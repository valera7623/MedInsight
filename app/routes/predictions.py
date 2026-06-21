import logging
from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import AnalysisJob, Patient, Prediction, User
from app.services.access import can_predict, can_view_patient, effective_tenant_id, patients_query
from app.services.email import get_email_service
from app.services.summarizer import generate_insights
from app.tasks.celery_app import redis_available
from app.tasks.predict_task import predict_risk_task

router = APIRouter(prefix="/analytics", tags=["predictions"])
logger = logging.getLogger(__name__)


class JobStartResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    status: str
    result: dict | None = None
    error: str | None = None


class PredictionResponse(BaseModel):
    id: int
    patient_id: int
    type: str
    prediction: dict | None
    probabilities: dict | None
    confidence_score: float
    validated: bool
    created_at: datetime
    expires_at: datetime | None

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
    return PredictionsListResponse(predictions=predictions)


@router.post("/insights/{patient_id}", response_model=InsightsResponse)
def patient_insights(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = _get_patient_or_404(db, patient_id, current_user, request)
    result = generate_insights(db, patient_id, current_user.id)
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
