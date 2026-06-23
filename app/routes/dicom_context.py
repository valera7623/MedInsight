"""DICOM clinical context API and DICOM-enriched prediction endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import AnalysisJob, DicomStudy, Patient, User
from app.services.access import can_predict, can_view_patient, effective_tenant_id
from app.services.dicom_rag import get_dicom_rag_service, is_dicom_rag_enabled
from app.services.dicom_text_extractor import DicomTextExtractor
from app.services.predictor import predict_risk_with_dicom
from app.tasks.celery_app import redis_available

logger = logging.getLogger(__name__)

dicom_router = APIRouter(prefix="/dicom", tags=["dicom-context"])
analytics_router = APIRouter(prefix="/analytics", tags=["predictions"])


class ClinicalContextResponse(BaseModel):
    study_uid: str
    clinical_context: str
    radiology_findings: list[str] = Field(default_factory=list)
    radiology_impression: str | None = None
    extracted_measurements: dict[str, Any] = Field(default_factory=dict)
    processed_at: datetime | None = None


class ProcessStudyResponse(BaseModel):
    study_uid: str
    status: str
    radiology_findings: list[str] = Field(default_factory=list)
    radiology_impression: str | None = None
    extracted_measurements: dict[str, Any] = Field(default_factory=dict)
    clinical_context_preview: str = ""
    indexed_in_rag: bool = False


class PredictWithDicomResponse(BaseModel):
    job_id: str
    status: str
    prediction_id: int | None = None
    prediction: dict | None = None
    dicom_sources: list[dict[str, Any]] = Field(default_factory=list)


def _ensure_dicom_enabled() -> None:
    if not settings.DICOM_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DICOM is disabled")


def _get_study_or_404(db: Session, study_uid: str, user: User, request: Request) -> DicomStudy:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    query = db.query(DicomStudy).filter(DicomStudy.study_uid == study_uid)
    if tid is not None:
        query = query.filter(DicomStudy.tenant_id == tid)
    study = query.first()
    if not study:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study not found")
    patient = db.query(Patient).filter(Patient.id == study.patient_id).first()
    if not patient or not can_view_patient(user, patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study not found")
    return study


def _get_patient_or_404(db: Session, patient_id: int, user: User, request: Request) -> Patient:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    query = db.query(Patient).filter(Patient.id == patient_id)
    if tid is not None:
        query = query.filter(Patient.tenant_id == tid)
    patient = query.first()
    if not patient or not can_view_patient(user, patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@dicom_router.get("/study/{study_uid}/clinical-context", response_model=ClinicalContextResponse)
def get_clinical_context(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_dicom_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)

    if not study.clinical_context:
        try:
            DicomTextExtractor(db).process_study(study_uid)
            db.refresh(study)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to build clinical context: {exc}",
            ) from exc

    return ClinicalContextResponse(
        study_uid=study.study_uid,
        clinical_context=study.clinical_context or "",
        radiology_findings=study.radiology_findings or [],
        radiology_impression=study.radiology_impression,
        extracted_measurements=study.extracted_measurements or {},
        processed_at=study.clinical_context_processed_at,
    )


@dicom_router.post("/study/{study_uid}/process", response_model=ProcessStudyResponse)
def process_study_context(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_dicom_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)
    if study.status != "ready":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Study is not ready")

    try:
        study = DicomTextExtractor(db).process_study(study_uid)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {exc}",
        ) from exc

    indexed = False
    if is_dicom_rag_enabled() and study.clinical_context:
        rag = get_dicom_rag_service()
        findings = study.radiology_findings or []
        rag.index_dicom_study(
            study_uid,
            clinical_context=study.clinical_context,
            metadata={
                "modality": study.modality,
                "body_part": study.body_part,
                "findings": findings,
            },
        )
        indexed = True

    preview = (study.clinical_context or "")[:500]
    return ProcessStudyResponse(
        study_uid=study.study_uid,
        status="processed",
        radiology_findings=study.radiology_findings or [],
        radiology_impression=study.radiology_impression,
        extracted_measurements=study.extracted_measurements or {},
        clinical_context_preview=preview,
        indexed_in_rag=indexed,
    )


@analytics_router.post("/predict-with-dicom/{patient_id}", response_model=PredictWithDicomResponse)
def predict_with_dicom(
    patient_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_predict(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot run predictions")
    _ensure_dicom_enabled()

    patient = _get_patient_or_404(db, patient_id, current_user, request)
    tenant_id = patient.tenant_id

    job = AnalysisJob(
        tenant_id=tenant_id,
        patient_id=patient_id,
        user_id=current_user.id,
        type="predict_dicom",
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    def _run_sync() -> PredictWithDicomResponse:
        job.status = "processing"
        db.commit()
        prediction = predict_risk_with_dicom(db, patient_id, current_user.id, job.id, tenant_id)
        job.status = "completed"
        job.result = {
            "prediction_id": prediction.id,
            "prediction": prediction.prediction,
            "dicom_sources": (prediction.prediction or {}).get("dicom_sources", []),
        }
        job.completed_at = datetime.utcnow()
        db.commit()
        return PredictWithDicomResponse(
            job_id=str(job.id),
            status="completed",
            prediction_id=prediction.id,
            prediction=prediction.prediction,
            dicom_sources=(prediction.prediction or {}).get("dicom_sources", []),
        )

    if not redis_available():
        result = _run_sync()
        return result

    try:
        from app.tasks.predict_task import predict_risk_dicom_task

        task = predict_risk_dicom_task.delay(job.id)
        job.celery_task_id = task.id
        db.commit()
    except Exception as exc:
        logger.warning("Celery unavailable for DICOM predict, running sync: %s", exc)
        db.rollback()
        return _run_sync()

    return PredictWithDicomResponse(job_id=str(job.id), status="pending")
