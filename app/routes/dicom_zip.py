"""DICOM ZIP upload, status and archive download API."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import DicomStudy, Patient, User
from app.routes.dicom import _ensure_dicom_enabled, _get_study_or_404
from app.services.access import can_view_patient, effective_tenant_id, is_super_admin
from app.services.audit import log_audit
from app.services.dicom_zip_processor import DicomZipProcessor, DicomZipError, SUPPORTED_ARCHIVE_SUFFIXES
from app.services.encryption import decrypt_file
from app.tasks.celery_app import celery_app, redis_available
from app.tasks.dicom_zip_task import process_dicom_zip

router = APIRouter(prefix="/dicom", tags=["dicom"])
logger = logging.getLogger(__name__)

ALLOWED_ARCHIVE_MIMES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/x-7z-compressed",
    "application/x-7z",
    "application/x-compressed",
    "application/octet-stream",
    "binary/octet-stream",
    "multipart/x-zip",
}


def _archive_upload_mime_ok(content_type: str | None, filename: str) -> bool:
    """Extension is authoritative; browser MIME labels for archives are often wrong."""
    if not content_type:
        return True
    ctype = content_type.split(";")[0].strip().lower()
    if ctype in ALLOWED_ARCHIVE_MIMES:
        return True
    return Path(filename).suffix.lower() in SUPPORTED_ARCHIVE_SUFFIXES


def _archive_media_type(filename: str) -> str:
    if filename.lower().endswith(".7z"):
        return "application/x-7z-compressed"
    return "application/zip"


async def _save_archive_stream(upload_file: UploadFile, dest: Path, max_bytes: int) -> int:
    """Stream multipart archive to disk with a size cap."""
    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await upload_file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Archive exceeds {settings.DICOM_ZIP_MAX_SIZE_MB} MB limit",
                    )
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        logger.exception("DICOM ZIP upload stream failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to save archive. Please retry.",
        ) from exc
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archive is empty")
    return size


class DicomZipUploadResponse(BaseModel):
    study_uid: str
    study_id: int
    job_id: str | None
    status: str
    total_files: int


class DicomZipStatusResponse(BaseModel):
    job_id: str
    status: str
    study_uid: str | None = None
    processed_files: int = 0
    total_files: int = 0
    percent: int = 0
    error: str | None = None


def _resolve_patient(
    db: Session,
    patient_id: int,
    current_user: User,
    request: Request,
) -> Patient:
    header_tid = get_request_tenant_id(request)
    patient_query = db.query(Patient).filter(Patient.id == patient_id)

    if is_super_admin(current_user):
        if header_tid is not None:
            patient_query = patient_query.filter(Patient.tenant_id == header_tid)
    elif current_user.tenant_id is not None:
        patient_query = patient_query.filter(Patient.tenant_id == current_user.tenant_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to a tenant. Re-login or contact admin.",
        )

    patient = patient_query.first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    if not can_view_patient(current_user, patient):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patient outside your scope")
    return patient


def _enqueue_zip(study_id: int, zip_path: str, user_id: int) -> str | None:
    if not redis_available():
        logger.info("Redis unavailable — sync DICOM ZIP processing for study %s", study_id)
        process_dicom_zip(study_id, zip_path, user_id)
        return None
    try:
        task = process_dicom_zip.delay(study_id, zip_path, user_id)
        return task.id
    except Exception as exc:
        logger.warning("Celery unavailable, sync DICOM ZIP: %s", exc)
        process_dicom_zip(study_id, zip_path, user_id)
        return None


@router.post("/upload-zip", response_model=DicomZipUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_dicom_zip(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    patient_id: int = Form(...),
    zip_file: UploadFile = File(...),
):
    _ensure_dicom_enabled()
    patient = _resolve_patient(db, patient_id, current_user, request)

    if not zip_file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    suffix = Path(zip_file.filename).suffix.lower()
    if suffix not in SUPPORTED_ARCHIVE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .zip and .7z archives are supported",
        )

    if not _archive_upload_mime_ok(zip_file.content_type, zip_file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type: {zip_file.content_type}",
        )

    max_bytes = settings.DICOM_ZIP_MAX_SIZE_MB * 1024 * 1024
    processor = DicomZipProcessor()
    zip_path = processor.temp_zip_path(suffix)
    zip_size = await _save_archive_stream(zip_file, zip_path, max_bytes)
    zip_size_mb = round(zip_size / (1024 * 1024), 2)

    try:
        entries = processor.iter_archive_dicom_paths(str(zip_path), integrity_check=False)
        total_files = len(entries)
    except DicomZipError as exc:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if total_files < 1:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archive must contain DICOM files and pass safety checks",
        )

    placeholder_uid = f"pending-zip-{uuid.uuid4().hex}"

    study = DicomStudy(
        patient_id=patient_id,
        tenant_id=patient.tenant_id,
        user_id=current_user.id,
        study_uid=placeholder_uid,
        original_filename=Path(zip_file.filename).name,
        status="processing",
        num_series=0,
        num_instances=0,
        total_files=total_files,
        processed_files=0,
        zip_size_mb=zip_size_mb,
    )
    db.add(study)
    db.commit()
    db.refresh(study)

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=patient.tenant_id,
        action="upload",
        resource_type="dicom_zip",
        resource_id=study.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"filename": study.original_filename, "patient_id": patient_id, "total_files": total_files},
    )

    job_id = _enqueue_zip(study.id, str(zip_path), current_user.id)
    db.refresh(study)

    return DicomZipUploadResponse(
        study_uid=study.study_uid,
        study_id=study.id,
        job_id=job_id,
        status=study.status,
        total_files=total_files,
    )


@router.get("/upload-zip/status/{job_id}", response_model=DicomZipStatusResponse)
def get_dicom_zip_status(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    study_id: int | None = None,
):
    _ensure_dicom_enabled()

    result = AsyncResult(job_id, app=celery_app)
    meta = result.info if isinstance(result.info, dict) else {}
    study_uid: str | None = meta.get("study_uid")
    processed = int(meta.get("processed", 0))
    total = int(meta.get("total", 0))
    percent = int(meta.get("percent", 0))
    error: str | None = None
    job_status = result.status or "PENDING"

    if study_id is not None:
        study = db.query(DicomStudy).filter(DicomStudy.id == study_id).first()
        if study and can_view_patient(current_user, study.patient):
            study_uid = study.study_uid if not study.study_uid.startswith("pending") else study_uid
            total = study.total_files or total
            processed = study.processed_files or processed
            if study.status == "ready":
                job_status = "SUCCESS"
                processed = total
                percent = 100
            elif study.status == "failed":
                job_status = "FAILURE"
                error = study.error_message
            elif study.status == "processing":
                job_status = "PROGRESS"
                percent = int(processed * 100 / total) if total else 0

    if job_status == "FAILURE":
        error = error or (str(result.info) if result.info else "Processing failed")
    if job_status == "SUCCESS":
        percent = 100

    return DicomZipStatusResponse(
        job_id=job_id,
        status=job_status,
        study_uid=study_uid,
        processed_files=processed,
        total_files=total,
        percent=percent,
        error=error,
    )


@router.get("/studies/{study_uid}/archive")
def download_dicom_archive(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_dicom_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)

    if not study.zip_original_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original ZIP archive not available")

    try:
        data = decrypt_file(study.zip_original_path)
    except Exception as exc:
        logger.exception("ZIP decrypt failed for study %s", study_uid)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to decrypt archive") from exc

    filename = study.original_filename or f"{study_uid}.zip"
    if not any(filename.lower().endswith(ext) for ext in SUPPORTED_ARCHIVE_SUFFIXES):
        filename = f"{filename}.zip"

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=study.tenant_id,
        action="download",
        resource_type="dicom_zip",
        resource_id=study.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"study_uid": study_uid},
    )

    return Response(
        content=data,
        media_type=_archive_media_type(filename),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
