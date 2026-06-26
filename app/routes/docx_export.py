"""DOCX export endpoints for patient cards and clinical reports."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.core.cache import cache_enabled, cache_service, docx_cache_key, docx_path_cache_key
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import Patient, User
from app.services.access import can_export, can_view_patient, effective_tenant_id
from app.services.audit import log_audit
from app.services.cache_invalidation import get_cache_version
from app.services.docx_generator import DocxGenerator, save_docx_to_patient_reports
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
    fallback = _ascii_filename_fallback(filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


def _load_docx_from_cache(db: Session, patient_id: int, options: dict) -> BytesIO | None:
    if not cache_enabled():
        return None
    version = get_cache_version(db, f"patient:{patient_id}")
    key = docx_cache_key(patient_id, options, version)
    cached = cache_service.get_bytes_sync(key)
    if cached:
        logger.info("DOCX sync cache HIT patient=%s", patient_id)
        buffer = BytesIO(cached)
        buffer.seek(0)
        return buffer
    path_key = docx_path_cache_key(patient_id, options, version)
    path_raw = cache_service.get_bytes_sync(path_key)
    if path_raw:
        path = Path(path_raw.decode("utf-8"))
        if path.exists():
            data = path.read_bytes()
            cache_service.set_bytes_sync(key, data, settings.REDIS_CACHE_DOCX_TTL)
            buffer = BytesIO(data)
            buffer.seek(0)
            return buffer
    return None


def _store_docx_cache(db: Session, patient_id: int, options: dict, buffer: BytesIO, file_path: str) -> None:
    if not cache_enabled():
        return
    version = get_cache_version(db, f"patient:{patient_id}")
    key = docx_cache_key(patient_id, options, version)
    path_key = docx_path_cache_key(patient_id, options, version)
    data = buffer.getvalue()
    cache_service.set_bytes_sync(key, data, settings.REDIS_CACHE_DOCX_TTL)
    cache_service.set_bytes_sync(path_key, file_path.encode("utf-8"), settings.REDIS_CACHE_DOCX_TTL)


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
        buffer = _load_docx_from_cache(db, patient.id, options)
        from_cache = buffer is not None
        if buffer is None:
            generator = DocxGenerator(db)
            buffer = generator.generate_patient_card(patient.id, options)
            file_path = save_docx_to_patient_reports(patient.id, buffer, suffix="patient_card")
            _store_docx_cache(db, patient.id, options, buffer, file_path)
            buffer.seek(0)
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
        headers={
            "Content-Disposition": _attachment_disposition(filename),
            "X-Cache": "HIT" if from_cache else "MISS",
        },
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
