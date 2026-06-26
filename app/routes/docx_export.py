"""DOCX export endpoints for patient cards and clinical reports."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import Patient, User
from app.services.access import can_export, can_view_patient, effective_tenant_id
from app.services.audit import log_audit
from app.services.docx_generator import DocxGenerator
from app.services.docx_templates import DEFAULT_PATIENT_CARD_SECTIONS
from app.tasks.celery_app import redis_available

router = APIRouter(prefix="/export", tags=["export"])
logger = logging.getLogger(__name__)

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class PatientCardExportRequest(BaseModel):
    patient_id: int
    format: Literal["docx"] = "docx"
    sections: list[str] = Field(default_factory=lambda: list(DEFAULT_PATIENT_CARD_SECTIONS))
    async_export: bool = False
    watermark: str | None = None


class PatientCardAsyncResponse(BaseModel):
    status: str
    job_id: str
    download_url: str
    message: str


def _get_patient_or_404(db: Session, patient_id: int, user: User, request: Request) -> Patient:
    tenant_id = effective_tenant_id(user, get_request_tenant_id(request))
    query = db.query(Patient).filter(Patient.id == patient_id)
    if tenant_id is not None:
        query = query.filter(Patient.tenant_id == tenant_id)
    patient = query.first()
    if not patient or not can_view_patient(user, patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


def _safe_docx_filename(patient: Patient) -> str:
    slug = f"{patient.last_name}_{patient.first_name}".replace(" ", "_")
    return f"patient_card_{patient.id}_{slug}_{datetime.utcnow():%Y%m%d}.docx"


def _ascii_filename_fallback(filename: str) -> str:
    ascii_name = re.sub(r"[^\w.\-]+", "_", filename, flags=re.ASCII)
    ascii_name = re.sub(r"_+", "_", ascii_name).strip("._")
    return ascii_name or "patient_card.docx"


def _attachment_disposition(filename: str) -> str:
    """HTTP headers must be latin-1; use RFC 5987 for Cyrillic filenames."""
    fallback = _ascii_filename_fallback(filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.post("/patient-card")
def export_patient_card_docx(
    body: PatientCardExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Generate a patient card as DOCX (sync) or enqueue Celery job (async_export=true)."""
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")

    if body.format != "docx":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only format=docx is supported")

    patient = _get_patient_or_404(db, body.patient_id, current_user, request)

    options = {
        "sections": body.sections,
        "watermark": body.watermark or settings.DOCX_WATERMARK,
    }

    if body.async_export:
        if not redis_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Async DOCX export requires Redis/Celery",
            )
        from app.tasks.docx_task import generate_patient_card_async

        task = generate_patient_card_async.delay(
            patient.id,
            options,
            current_user.id,
            patient.tenant_id,
        )
        return PatientCardAsyncResponse(
            status="processing",
            job_id=task.id,
            download_url=f"/api/export/patient-card/download/{task.id}",
            message="Генерация DOCX выполняется асинхронно. Скачайте файл по download_url.",
        )

    try:
        generator = DocxGenerator(db)
        buffer = generator.generate_patient_card(patient.id, options)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("DOCX patient card export failed for patient %s", patient.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate DOCX",
        ) from exc

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=patient.tenant_id,
        action="export",
        resource_type="patient_docx",
        resource_id=patient.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"format": "docx", "sections": body.sections},
    )

    filename = _safe_docx_filename(patient)
    return StreamingResponse(
        buffer,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": _attachment_disposition(filename)},
    )


@router.get("/patient-card/download/{job_id}")
def download_async_patient_card(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Download DOCX generated by Celery task."""
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")

    from celery.result import AsyncResult

    from app.tasks.celery_app import celery_app

    result = AsyncResult(job_id, app=celery_app)
    if not result.ready():
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Export still processing")

    if result.failed():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(result.result) if result.result else "DOCX export failed",
        )

    payload = result.get()
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid export result")

    file_path = Path(payload["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found")

    patient_id = payload.get("patient_id")
    if patient_id:
        patient = _get_patient_or_404(db, int(patient_id), current_user, request)
        log_audit(
            db,
            user_id=current_user.id,
            tenant_id=patient.tenant_id,
            action="download",
            resource_type="patient_docx",
            resource_id=patient.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={"job_id": job_id, "async": True},
        )

    return FileResponse(
        path=file_path,
        media_type=DOCX_MEDIA,
        filename=file_path.name,
    )
