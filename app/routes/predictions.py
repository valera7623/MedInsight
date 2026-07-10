import logging
from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import rate_limit
from app.middleware.tenant import get_request_tenant_id
from app.models import AnalysisJob, Patient, Prediction, User
from app.services.access import can_predict, can_view_patient, effective_tenant_id, patients_query
from app.services.email import get_email_service
from app.services.list_queries import PREDICTION_SORT, predictions_scope
from app.services.summarizer import generate_insights
from app.utils.pagination import PaginationParams, paginate
from app.tasks.celery_app import redis_available
from app.tasks.predict_task import predict_risk_task

router = APIRouter(prefix="/analytics", tags=["predictions"])
logger = logging.getLogger(__name__)


class JobStartResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    status: str
    result: dict | None = Field(
        default=None,
        description="Includes prediction, probabilities, shap, ml when job completes",
    )
    error: str | None = None


class ShapContribution(BaseModel):
    """Single feature contribution from SHAP (local explanation)."""
    feature: str = Field(description="Encoded feature name, e.g. age, diagnosis_count")
    value: float = Field(description="Raw feature value for this patient")
    shap: float = Field(description="SHAP value — contribution to model output")


class ShapLocalExplanation(BaseModel):
    """Local SHAP explanation for one prediction (force/waterfall plot data)."""
    target: str = Field(default="readmission", description="Prediction target explained")
    model_type: str = Field(description="Underlying model: random_forest or xgboost")
    base_value: float = Field(description="Model expected value (baseline)")
    output_value: float = Field(description="base_value + sum(SHAP contributions)")
    contributions: list[ShapContribution] = Field(description="Per-feature SHAP values, sorted by |shap|")
    top_features: list[ShapContribution] = Field(description="Top-10 features by impact")
    waterfall: dict = Field(description="Steps for waterfall chart on frontend")
    cached: bool = Field(default=False, description="Whether result was served from Redis cache")


class ShapSummaryBarItem(BaseModel):
    feature: str
    mean_abs_shap: float = Field(description="Mean |SHAP| across background sample — summary bar plot")


class ShapBeeswarmPoint(BaseModel):
    feature: str
    feature_value: float
    shap_value: float


class ShapGlobalSummary(BaseModel):
    """Global SHAP summary plot data (bar + beeswarm) for model-wide explainability."""
    target: str
    tenant_id: int
    model_type: str
    sample_size: int
    feature_names: list[str]
    summary_bar: list[ShapSummaryBarItem] = Field(description="Mean |SHAP| per feature — horizontal bar chart")
    beeswarm: list[ShapBeeswarmPoint] = Field(description="Points for beeswarm / dot plot")
    cached: bool = False


class MlPredictionInfo(BaseModel):
    model_type: str
    probability_high_readmission: float = Field(description="P(high readmission) from tabular ML model")
    probability_low_readmission: float
    predicted_class: str = Field(description="high or low")
    risk_percent: float = Field(description="High-readmission probability as 0–100%")


class PredictionResponse(BaseModel):
    id: int
    patient_id: int
    type: str
    prediction: dict | None = Field(
        description="Risk scores, factors, and optional shap/ml sub-objects"
    )
    probabilities: dict | None
    confidence_score: float
    validated: bool
    created_at: datetime
    expires_at: datetime | None
    shap: dict | None = Field(
        default=None,
        description="SHAP local explanation (mirrors prediction.shap when present)",
    )
    ml: dict | None = Field(
        default=None,
        description="Tabular ML classifier output (mirrors prediction.ml when present)",
    )

    model_config = {"from_attributes": True}


class PredictionsListResponse(BaseModel):
    predictions: list[PredictionResponse]


class InsightsResponse(BaseModel):
    insights: str
    recommendations: list[str]


class ValidateResponse(BaseModel):
    status: str


class HighRiskPatient(BaseModel):
    id: int
    name: str
    readmission_risk: float
    complication_risk: float
    last_prediction_at: str


class PredictionsDashboardResponse(BaseModel):
    high_risk_patients: list[HighRiskPatient]
    risk_by_department: dict[str, dict[str, float]]
    monthly_trends: dict[str, list]


def _serialize_prediction(p: Prediction) -> dict:
    data = PredictionResponse.model_validate(p).model_dump(mode="json")
    pred = p.prediction or {}
    if pred.get("shap"):
        data["shap"] = pred["shap"]
    if pred.get("ml"):
        data["ml"] = pred["ml"]
    return data


def _get_prediction_or_404(
    db: Session, prediction_id: int, user: User, request: Request
) -> Prediction:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    query = db.query(Prediction).filter(Prediction.id == prediction_id)
    if tid is not None:
        query = query.filter(Prediction.tenant_id == tid)
    prediction = query.first()
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
    patient = db.query(Patient).filter(Patient.id == prediction.patient_id).first()
    if not patient or not can_view_patient(user, patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
    return prediction


def _get_patient_or_404(db: Session, patient_id: int, user: User, request: Request) -> Patient:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    query = db.query(Patient).filter(Patient.id == patient_id)
    if tid is not None:
        query = query.filter(Patient.tenant_id == tid)
    patient = query.first()
    if not patient or not can_view_patient(user, patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


def _get_job_or_404(db: Session, job_id: int, user: User, request: Request) -> AnalysisJob:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    query = db.query(AnalysisJob).filter(AnalysisJob.id == job_id)
    if tid is not None:
        query = query.filter(AnalysisJob.tenant_id == tid)
    job = query.first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/predict/{patient_id}", response_model=JobStartResponse)
@rate_limit(
    limit=settings.RATE_LIMIT_PREDICT_PER_MINUTE,
    period=60,
    name="analytics_predict",
)
def start_prediction(
    patient_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_predict(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot run predictions")

    patient = _get_patient_or_404(db, patient_id, current_user, request)
    tenant_id = patient.tenant_id
    patient_name = f"{patient.last_name} {patient.first_name}".strip()
    notify_email = current_user.email

    job = AnalysisJob(
        tenant_id=tenant_id,
        patient_id=patient_id,
        user_id=current_user.id,
        type="predict",
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Consume one analysis credit for the tenant (Phase 4 billing).
    if tenant_id is not None:
        try:
            from app.services.payment.usage_tracker import increment_usage

            increment_usage(tenant_id)
        except Exception as exc:
            logger.warning("Usage increment failed for tenant %s: %s", tenant_id, exc)

    def _run_sync() -> None:
        from app.services.predictor import predict_risk

        job.status = "processing"
        db.commit()
        prediction = predict_risk(db, patient_id, current_user.id, job.id, tenant_id)
        job.status = "completed"
        job.result = {
            "prediction_id": prediction.id,
            "prediction": prediction.prediction,
            "probabilities": prediction.probabilities,
            "confidence_score": prediction.confidence_score,
            "shap": (prediction.prediction or {}).get("shap"),
            "ml": (prediction.prediction or {}).get("ml"),
        }
        job.completed_at = datetime.utcnow()
        db.commit()
        try:
            from app.tasks.webhook_task import fire_event

            fire_event(
                "prediction.ready",
                tenant_id,
                patient_id=patient_id,
                analysis_id=job.id,
                prediction_id=prediction.id,
                result=prediction.prediction,
            )
        except Exception as exc:
            logger.warning("Webhook dispatch failed (sync predict): %s", exc)

        if settings.EMAIL_PREDICTION_READY_ENABLED and notify_email:
            background_tasks.add_task(
                get_email_service().send_prediction_ready_email,
                notify_email,
                patient_name,
                job.result["prediction_id"],
            )

        try:
            from app.websocket.events import (
                EVENT_ANALYSIS_COMPLETED,
                EVENT_PREDICTION_READY,
                publish_event,
            )

            pred_data = prediction.prediction or {}
            publish_event(
                EVENT_PREDICTION_READY,
                {
                    "patient_id": patient_id,
                    "prediction_id": prediction.id,
                    "type": prediction.type,
                    "risk": round(float(pred_data.get("readmission_risk", 0))),
                    "confidence": round(float(prediction.confidence_score or 0), 2),
                },
                user_id=current_user.id,
                tenant_id=tenant_id,
            )
            publish_event(
                EVENT_ANALYSIS_COMPLETED,
                {"patient_id": patient_id, "analysis_id": job.id, "type": "predict"},
                user_id=current_user.id,
                tenant_id=tenant_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("WS prediction event failed: %s", exc)

    if not redis_available():
        logger.info("Redis unavailable — running sync prediction for job %s", job.id)
        _run_sync()
        return JobStartResponse(job_id=str(job.id), status="completed")

    try:
        task = predict_risk_task.delay(job.id)
        job.celery_task_id = task.id
        db.commit()
    except Exception as exc:
        logger.warning("Celery unavailable, running sync prediction: %s", exc)
        db.rollback()
        _run_sync()
        return JobStartResponse(job_id=str(job.id), status="completed")

    return JobStartResponse(job_id=str(job.id), status="pending")


@router.get("/predict/status/{job_id}", response_model=JobStatusResponse)
def prediction_status(
    job_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    job = _get_job_or_404(db, job_id, current_user, request)
    return JobStatusResponse(
        status=job.status,
        result=job.result,
        error=job.error_message,
    )


@router.get("/predictions")
def list_predictions_all(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    patient_id: int | None = Query(None),
    type: str | None = Query(None),
    validated: bool | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    query = predictions_scope(db, current_user, tid)
    params = PaginationParams(
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={"patient_id": patient_id, "type": type, "validated": validated},
    )
    return paginate(
        query,
        params,
        model=Prediction,
        allowed_sort=PREDICTION_SORT,
        serializer=lambda p: _serialize_prediction(p),
    )


@router.get("/predictions/shap/summary", response_model=ShapGlobalSummary)
def get_shap_summary(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    target: str = Query("readmission", description="Prediction target for global SHAP summary"),
    sample_size: int | None = Query(None, ge=50, le=500),
):
    """Global SHAP summary plot data (mean |SHAP| bar + beeswarm points)."""
    if not settings.SHAP_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SHAP disabled")

    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant required")

    from app.services.shap_explainer import get_shap_explainer

    data = get_shap_explainer().explain_global(tid, target=target, sample_size=sample_size)
    return ShapGlobalSummary(**data)


@router.get("/predictions/detail/{prediction_id}", response_model=PredictionResponse)
def get_prediction_detail(
    prediction_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get a single prediction including SHAP and ML explanation fields."""
    prediction = _get_prediction_or_404(db, prediction_id, current_user, request)
    return _serialize_prediction(prediction)


@router.get("/predictions/shap/local/{prediction_id}", response_model=ShapLocalExplanation)
def get_prediction_shap(
    prediction_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Local SHAP explanation for a stored prediction (cached in Redis)."""
    if not settings.SHAP_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SHAP disabled")

    prediction = _get_prediction_or_404(db, prediction_id, current_user, request)
    pred = prediction.prediction or {}
    shap_block = pred.get("shap") or {}
    if shap_block.get("status") == "ready" and shap_block.get("local"):
        return ShapLocalExplanation(**shap_block["local"])

    from app.services.shap_explainer import get_shap_explainer

    features = prediction.features or {}
    local = get_shap_explainer().explain_local(features, prediction_id=prediction_id)
    return ShapLocalExplanation(**local)


@router.post("/predictions/shap/compute/{prediction_id}")
def compute_shap_async(
    prediction_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Enqueue async SHAP computation (Celery) for an existing prediction."""
    if not settings.SHAP_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SHAP disabled")

    prediction = _get_prediction_or_404(db, prediction_id, current_user, request)

    from app.tasks.celery_app import redis_available
    from app.tasks.shap_task import compute_shap_values_task

    if not redis_available():
        from app.services.shap_explainer import attach_shap_to_prediction_dict

        features = prediction.features or {}
        pred_data = attach_shap_to_prediction_dict(
            features, dict(prediction.prediction or {}), prediction_id=prediction.id
        )
        prediction.prediction = pred_data
        db.commit()
        return {"status": "completed", "prediction_id": prediction.id, "mode": "sync"}

    task = compute_shap_values_task.delay(prediction.id)
    return {"status": "pending", "prediction_id": prediction.id, "task_id": task.id}


@router.get("/predictions/{patient_id}", response_model=PredictionsListResponse)
def list_predictions(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = _get_patient_or_404(db, patient_id, current_user, request)

    predictions = (
        db.query(Prediction)
        .filter(Prediction.patient_id == patient_id, Prediction.tenant_id == patient.tenant_id)
        .order_by(Prediction.created_at.desc())
        .all()
    )
    return PredictionsListResponse(
        predictions=[_serialize_prediction(p) for p in predictions]
    )


@router.post("/insights/{patient_id}", response_model=InsightsResponse)
def patient_insights(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = _get_patient_or_404(db, patient_id, current_user, request)
    result = generate_insights(db, patient_id, current_user.id, patient.tenant_id)
    return InsightsResponse(
        insights=result.get("summary", ""),
        recommendations=result.get("recommendations", []),
    )


@router.post("/validate-prediction/{prediction_id}", response_model=ValidateResponse)
def validate_prediction(
    prediction_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    prediction = (
        db.query(Prediction)
        .filter(Prediction.id == prediction_id, Prediction.tenant_id == effective_tenant_id(current_user, get_request_tenant_id(request)))
        .first()
    )
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")

    prediction.validated = True
    prediction.validated_at = datetime.utcnow()
    db.commit()
    return ValidateResponse(status="validated")


@router.get("/dashboard/predictions", response_model=PredictionsDashboardResponse)
def predictions_dashboard(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    department_id: int | None = Query(None),
):
    # Scope predictions to the patients this user is allowed to see.
    pq = patients_query(db, current_user, get_request_tenant_id(request))
    if department_id is not None:
        pq = pq.filter(Patient.department_id == department_id)
    accessible_ids = [p.id for p in pq.all()]
    if not accessible_ids:
        return PredictionsDashboardResponse(
            high_risk_patients=[], risk_by_department={}, monthly_trends={"labels": [], "readmission": [], "complication": []}
        )
    predictions = (
        db.query(Prediction)
        .filter(Prediction.patient_id.in_(accessible_ids))
        .order_by(Prediction.created_at.desc())
        .all()
    )

    latest_by_patient: dict[int, Prediction] = {}
    for pred in predictions:
        if pred.patient_id not in latest_by_patient:
            latest_by_patient[pred.patient_id] = pred

    high_risk: list[HighRiskPatient] = []
    dept_readmission: dict[str, list[float]] = defaultdict(list)
    dept_complication: dict[str, list[float]] = defaultdict(list)
    monthly_readmission: dict[str, list[float]] = defaultdict(list)
    monthly_complication: dict[str, list[float]] = defaultdict(list)

    for patient_id, pred in latest_by_patient.items():
        if not pred.prediction:
            continue

        readmission = float(pred.prediction.get("readmission_risk", 0))
        complication = float(pred.prediction.get("complication_risk", 0))

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            continue

        name = f"{patient.last_name} {patient.first_name}"
        if readmission >= 60 or complication >= 60:
            high_risk.append(
                HighRiskPatient(
                    id=patient_id,
                    name=name,
                    readmission_risk=readmission,
                    complication_risk=complication,
                    last_prediction_at=pred.created_at.isoformat(),
                )
            )

        dept = "Общее"
        if patient.documents:
            dept = patient.documents[0].document_type or "Общее"

        dept_readmission[dept].append(readmission)
        dept_complication[dept].append(complication)

        month_key = pred.created_at.strftime("%Y-%m")
        monthly_readmission[month_key].append(readmission)
        monthly_complication[month_key].append(complication)

    high_risk.sort(key=lambda p: max(p.readmission_risk, p.complication_risk), reverse=True)

    risk_by_department: dict[str, dict[str, float]] = {}
    for dept in set(dept_readmission.keys()) | set(dept_complication.keys()):
        read_vals = dept_readmission.get(dept, [])
        comp_vals = dept_complication.get(dept, [])
        risk_by_department[dept] = {
            "readmission_avg": round(sum(read_vals) / len(read_vals), 1) if read_vals else 0,
            "complication_avg": round(sum(comp_vals) / len(comp_vals), 1) if comp_vals else 0,
            "patient_count": len(read_vals),
        }

    all_months = sorted(set(monthly_readmission.keys()) | set(monthly_complication.keys()))
    monthly_trends = {
        "labels": all_months,
        "readmission": [
            round(sum(monthly_readmission[m]) / len(monthly_readmission[m]), 1) if monthly_readmission[m] else 0
            for m in all_months
        ],
        "complication": [
            round(sum(monthly_complication[m]) / len(monthly_complication[m]), 1) if monthly_complication[m] else 0
            for m in all_months
        ],
    }

    return PredictionsDashboardResponse(
        high_risk_patients=high_risk[:10],
        risk_by_department=risk_by_department,
        monthly_trends=monthly_trends,
    )
