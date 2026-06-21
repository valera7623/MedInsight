"""DICOM upload, listing, viewing and management API (Phase 12)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import DicomStudy, Patient, User
from app.services.access import can_view_patient, effective_tenant_id, is_admin, is_super_admin
from app.services.audit import log_audit
from app.services.dicom_storage import DicomStorage
from app.services.dicom_viewer import DicomViewer
from app.services.list_queries import DICOM_SEARCH_FIELDS, DICOM_SORT, dicom_studies_scope
from app.tasks.celery_app import redis_available
from app.tasks.dicom_task import process_dicom_study
from app.utils.pagination import PaginationParams, paginate

router = APIRouter(prefix="/dicom", tags=["dicom"])
logger = logging.getLogger(__name__)

ALLOWED_DICOM_MIMES = {
    "application/dicom",
    "application/octet-stream",
    "application/dicom+json",
}


class DicomStudySummary(BaseModel):
    id: int
    study_uid: str
    patient_id: int
    tenant_id: int
    study_date: datetime | None
    study_description: str | None
    modality: str | None
    body_part: str | None
    patient_name_dicom: str | None
    num_series: int
    num_instances: int
    status: str
    created_at: datetime
    processed_at: datetime | None
    thumbnail_url: str | None = None

    model_config = {"from_attributes": True}


class DicomUploadResponse(BaseModel):
    study_uid: str
    study_id: int
    job_id: str | None
    status: str


def _ensure_dicom_enabled() -> None:
    if not settings.DICOM_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DICOM support is disabled")


def _get_study_or_404(
    db: Session,
    study_uid: str,
    user: User,
    request: Request | None = None,
) -> DicomStudy:
    tid = effective_tenant_id(user, get_request_tenant_id(request) if request else None)
    query = db.query(DicomStudy).filter(DicomStudy.study_uid == study_uid)
    if tid is not None:
        query = query.filter(DicomStudy.tenant_id == tid)
    study = query.first()
    if not study:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DICOM study not found")
    if study.patient is not None and not can_view_patient(user, study.patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DICOM study not found")
    return study


def _serialize_study(study: DicomStudy, viewer: DicomViewer | None = None) -> dict:
    thumb = viewer.get_thumbnail(study.study_uid) if viewer and study.status == "ready" else None
    data = DicomStudySummary.model_validate(study).model_dump()
    data["thumbnail_url"] = thumb
    return data


def _enqueue_dicom(study_id: int, temp_path: str) -> str | None:
    if not redis_available():
        logger.info("Redis unavailable — sync DICOM processing for study %s", study_id)
        process_dicom_study(study_id, temp_path)
        return None
    try:
        task = process_dicom_study.delay(study_id, temp_path)
        return task.id
    except Exception as exc:
        logger.warning("Celery unavailable, falling back to sync DICOM processing: %s", exc)
        process_dicom_study(study_id, temp_path)
        return None


@router.post("/upload", response_model=DicomUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_dicom(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    patient_id: int = Form(...),
    file: UploadFile = File(...),
):
    _ensure_dicom_enabled()

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

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix and suffix not in {".dcm", ".dicom"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only DICOM (.dcm) files are supported")

    if file.content_type and file.content_type not in ALLOWED_DICOM_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type: {file.content_type}",
        )

    content = await file.read()
    max_bytes = settings.DICOM_MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.DICOM_MAX_FILE_SIZE_MB} MB limit",
        )

    storage = DicomStorage()
    temp_path = storage.temp_upload_path(suffix=suffix or ".dcm")
    temp_path.write_bytes(content)

    placeholder_uid = f"pending-{uuid.uuid4().hex}"
    study = DicomStudy(
        patient_id=patient_id,
        tenant_id=patient.tenant_id,
        user_id=current_user.id,
        study_uid=placeholder_uid,
        original_filename=Path(file.filename).name,
        status="processing",
        num_series=0,
        num_instances=0,
    )
    db.add(study)
    db.commit()
    db.refresh(study)

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=patient.tenant_id,
        action="upload",
        resource_type="dicom_study",
        resource_id=study.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"filename": study.original_filename, "patient_id": patient_id},
    )

    job_id = _enqueue_dicom(study.id, str(temp_path))
    db.refresh(study)

    return DicomUploadResponse(
        study_uid=study.study_uid,
        study_id=study.id,
        job_id=job_id,
        status=study.status,
    )


@router.get("/studies")
def list_dicom_studies(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    patient_id: int | None = Query(None),
    modality: str | None = Query(None),
    study_status: str | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    _ensure_dicom_enabled()
    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    query = dicom_studies_scope(db, current_user, tid)

    if date_from is not None:
        query = query.filter(DicomStudy.study_date >= date_from)
    if date_to is not None:
        query = query.filter(DicomStudy.study_date <= date_to)

    viewer = DicomViewer(db)
    params = PaginationParams(
        page=page,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={"patient_id": patient_id, "modality": modality, "status": study_status},
    )
    return paginate(
        query,
        params,
        model=DicomStudy,
        search_fields=DICOM_SEARCH_FIELDS,
        allowed_sort=DICOM_SORT,
        serializer=lambda s: _serialize_study(s, viewer),
    )


@router.get("/studies/{study_uid}")
def get_dicom_study(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_dicom_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)
    viewer = DicomViewer(db)
    info = viewer.get_study_info(study.study_uid)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DICOM study not found")
    info["thumbnail_url"] = viewer.get_thumbnail(study.study_uid)
    return info


@router.get("/studies/{study_uid}/series/{series_uid}/frames")
def list_series_frames(
    study_uid: str,
    series_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_dicom_enabled()
    _get_study_or_404(db, study_uid, current_user, request)
    viewer = DicomViewer(db)
    info = viewer.get_series_info(series_uid)
    if not info or info.get("study_uid") != study_uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return {"frames": info["frames"]}


@router.get("/studies/{study_uid}/thumbnail")
def get_study_thumbnail(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_dicom_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)
    viewer = DicomViewer(db)
    thumb_url = viewer.get_thumbnail(study.study_uid)
    if not thumb_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available")

    instance_uid = thumb_url.split("/api/dicom/frames/")[1].split("?")[0]
    frame = viewer.resolve_frame(instance_uid, study_uid=study_uid)
    if not frame or not Path(frame.image_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available")

    return FileResponse(frame.image_path, media_type="image/png")


@router.get("/frames/{instance_uid}")
def get_dicom_frame(
    instance_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    study_uid: str | None = Query(None),
    frame: int = Query(0, ge=0),
):
    _ensure_dicom_enabled()
    viewer = DicomViewer(db)

    if study_uid:
        _get_study_or_404(db, study_uid, current_user, request)

    dicom_frame = viewer.resolve_frame(instance_uid, study_uid=study_uid)
    if not dicom_frame:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")

    series = dicom_frame.series
    study = series.study if series else None
    if not study or not can_view_patient(current_user, study.patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")

    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tid is not None and study.tenant_id != tid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")

    path = Path(dicom_frame.image_path)
    if not path.exists():
        storage = DicomStorage()
        alt = storage.get_frame_path(study.patient_id, study.study_uid, instance_uid, frame)
        if not alt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found")
        path = Path(alt)

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=study.tenant_id,
        action="view",
        resource_type="dicom_frame",
        resource_id=dicom_frame.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"instance_uid": instance_uid, "study_uid": study.study_uid},
    )

    return FileResponse(
        path,
        media_type="image/png",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"},
    )


@router.delete("/studies/{study_uid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dicom_study(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_dicom_enabled()
    if not is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    study = _get_study_or_404(db, study_uid, current_user, request)
    storage = DicomStorage()

    if study.file_path_encrypted:
        try:
            Path(study.file_path_encrypted).unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete encrypted DICOM %s: %s", study.file_path_encrypted, exc)

    storage.delete_study(study.patient_id, study.study_uid)
    study_id = study.id
    tenant_id = study.tenant_id
    db.delete(study)
    db.commit()

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=tenant_id,
        action="delete",
        resource_type="dicom_study",
        resource_id=study_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"study_uid": study_uid},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
