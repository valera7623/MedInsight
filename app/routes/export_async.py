"""Async DOCX export status/download with multi-tier cache."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.routes.docx_export import (
    DOCX_MEDIA,
    _attachment_disposition,
    _get_patient_or_404,
    _safe_docx_filename,
)
from app.services.access import can_export
from app.services.audit import log_audit
from app.services.cache_manager import get_cache_manager
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/export", tags=["export"])
logger = logging.getLogger(__name__)


class ExportStatusResponse(BaseModel):
    job_id: str
    state: str
    ready: bool
    status: str | None = None
    cache_hit: bool = False
    cache_source: str | None = None
    patient_id: int | None = None
    error: str | None = None


def _resolve_task_payload(result: AsyncResult) -> dict | None:
    if not result.ready():
        return None
    if result.failed():
        return {"status": "failed", "error": str(result.result)}
    payload = result.get()
    return payload if isinstance(payload, dict) else None


def _try_cache_bytes(db: Session, payload: dict) -> tuple[bytes | None, str | None]:
    patient_id = payload.get("patient_id")
    options = payload.get("options")
    if patient_id is None or not isinstance(options, dict):
        return None, None
    mgr = get_cache_manager(db)
    return mgr.get_docx_sync(int(patient_id), options)


@router.get("/status/{job_id}", response_model=ExportStatusResponse)
def export_status(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")

    result = AsyncResult(job_id, app=celery_app)
    payload = _resolve_task_payload(result)
    cache_hit = False
    cache_source = None
    patient_id = None
    task_status = None
    error = None

    if payload:
        task_status = payload.get("status")
        patient_id = payload.get("patient_id")
        error = payload.get("error")
        data, cache_source = _try_cache_bytes(db, payload)
        cache_hit = data is not None
    elif not result.ready():
        task_status = "processing"
    elif result.failed():
        task_status = "failed"
        error = str(result.result)

    return ExportStatusResponse(
        job_id=job_id,
        state=result.state,
        ready=result.ready(),
        status=task_status,
        cache_hit=cache_hit,
        cache_source=cache_source,
        patient_id=patient_id,
        error=error,
    )


@router.get("/download/{job_id}")
def export_download(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")

    result = AsyncResult(job_id, app=celery_app)
    if not result.ready():
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Export still processing")

    if result.failed():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(result.result) if result.result else "Export failed",
        )

    payload = result.get()
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid export result")

    patient_id = payload.get("patient_id")
    options = payload.get("options") or {}
    cache_source = "generated"
    docx_bytes: bytes | None = None

    if patient_id is not None:
        mgr = get_cache_manager(db)
        docx_bytes, cache_source = mgr.get_docx_sync(int(patient_id), options)

    if docx_bytes is None:
        file_path = Path(payload.get("file_path", ""))
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found")
        docx_bytes = file_path.read_bytes()
        cache_source = payload.get("cache_source") or "filesystem"

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
            details={"job_id": job_id, "async": True, "cache_source": cache_source},
        )
        filename = _safe_docx_filename(patient)
    else:
        filename = f"patient_card_{job_id}.docx"

    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type=DOCX_MEDIA,
        headers={
            "Content-Disposition": _attachment_disposition(filename),
            "X-Cache": cache_source.upper() if cache_source else "MISS",
        },
    )
