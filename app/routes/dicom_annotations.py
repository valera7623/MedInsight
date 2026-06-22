"""DICOM annotation API — markup on frames (Phase 12c)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import DicomFrame, User
from app.services.access import can_view_patient, effective_tenant_id, require_tenant_access
from app.services.audit import log_audit
from app.services.dicom_annotations import (
    AnnotationError,
    DicomAnnotationService,
    get_frame_by_instance_uid,
    get_frame_with_study,
)

router = APIRouter(prefix="/dicom/annotations", tags=["dicom-annotations"])
logger = logging.getLogger(__name__)


class AnnotationCreate(BaseModel):
    frame_id: int
    type: str
    coordinates: dict[str, Any] = Field(default_factory=dict)
    color: str = "#FF0000"
    label: str | None = None
    measurement_value: float | None = None
    measurement_unit: str | None = None


class AnnotationUpdate(BaseModel):
    type: str | None = None
    coordinates: dict[str, Any] | None = None
    color: str | None = None
    label: str | None = None
    measurement_value: float | None = None
    measurement_unit: str | None = None


class AnnotationResponse(BaseModel):
    id: int
    frame_id: int
    user_id: int
    type: str
    coordinates: dict[str, Any]
    color: str
    label: str | None
    measurement_value: float | None
    measurement_unit: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    study_uid: str
    series_uid: str
    frame_instance_uid: str


class SessionResponse(BaseModel):
    id: int
    user_id: int
    study_uid: str
    series_uid: str
    frame_instance_uid: str
    opened_at: datetime | None
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class ImportBody(BaseModel):
    json_data: str
    replace: bool = False


def _ensure_enabled() -> None:
    if not settings.DICOM_ANNOTATIONS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DICOM annotations are disabled",
        )


def _audit(
    db: Session,
    request: Request,
    user: User,
    action: str,
    resource_id: int | None,
    details: dict | None = None,
) -> None:
    log_audit(
        db,
        user_id=user.id,
        tenant_id=effective_tenant_id(user, get_request_tenant_id(request)),
        action=action,
        resource_type="dicom_annotation",
        resource_id=resource_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _require_frame_access(db: Session, user: User, frame_id: int, request: Request) -> DicomFrame:
    frame = get_frame_with_study(db, frame_id)
    if not frame or not frame.series or not frame.series.study:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    study = frame.series.study
    if study.tenant_id is not None:
        tid = effective_tenant_id(user, get_request_tenant_id(request))
        if tid is not None:
            require_tenant_access(user, study.tenant_id)
    patient = study.patient
    if patient is not None and not can_view_patient(user, patient):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return frame


def _require_instance_access(
    db: Session, user: User, instance_uid: str, request: Request
) -> DicomFrame:
    frame = get_frame_by_instance_uid(db, instance_uid)
    if not frame:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    return _require_frame_access(db, user, frame.id, request)


@router.post("", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
def create_annotation(
    body: AnnotationCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    _require_frame_access(db, current_user, body.frame_id, request)
    svc = DicomAnnotationService(db)
    try:
        ann = svc.create_annotation(body.model_dump(), user_id=current_user.id)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit(db, request, current_user, "dicom_annotation.create", ann.id, {"type": ann.type})
    return ann


@router.get("/frame/{frame_id}", response_model=list[AnnotationResponse])
def list_annotations_by_frame(
    frame_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    _require_frame_access(db, current_user, frame_id, request)
    return DicomAnnotationService(db).get_annotations(frame_id)


@router.get("/frame-instance/{frame_instance_uid}", response_model=list[AnnotationResponse])
def list_annotations_by_instance(
    frame_instance_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    frame = _require_instance_access(db, current_user, frame_instance_uid, request)
    return DicomAnnotationService(db).get_annotations(frame.id)


@router.put("/{annotation_id}", response_model=AnnotationResponse)
def update_annotation(
    annotation_id: int,
    body: AnnotationUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    svc = DicomAnnotationService(db)
    ann = svc.get_annotation(annotation_id)
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    _require_frame_access(db, current_user, ann.frame_id, request)
    try:
        updated = svc.update_annotation(
            annotation_id, body.model_dump(exclude_unset=True), user_id=current_user.id
        )
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit(db, request, current_user, "dicom_annotation.update", annotation_id)
    return updated


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(
    annotation_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    svc = DicomAnnotationService(db)
    ann = svc.get_annotation(annotation_id)
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    _require_frame_access(db, current_user, ann.frame_id, request)
    try:
        svc.delete_annotation(annotation_id, user_id=current_user.id)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    _audit(db, request, current_user, "dicom_annotation.delete", annotation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/frame/{frame_id}")
def delete_frame_annotations(
    frame_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    _require_frame_access(db, current_user, frame_id, request)
    count = DicomAnnotationService(db).batch_delete_annotations(frame_id, user_id=current_user.id)
    _audit(db, request, current_user, "dicom_annotation.batch_delete", frame_id, {"count": count})
    return {"deleted": count}


@router.post("/export/{frame_id}")
def export_annotations_json(
    frame_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    anonymize: bool = Query(False),
):
    _ensure_enabled()
    _require_frame_access(db, current_user, frame_id, request)
    payload = DicomAnnotationService(db).export_annotations_to_json(frame_id, anonymize=anonymize)
    _audit(db, request, current_user, "dicom_annotation.export", frame_id, {"format": "json"})
    return JSONResponse(content={"json": payload})


@router.get("/export/{frame_id}/geojson")
def export_annotations_geojson(
    frame_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    _require_frame_access(db, current_user, frame_id, request)
    payload = DicomAnnotationService(db).export_annotations_to_geojson(frame_id)
    _audit(db, request, current_user, "dicom_annotation.export", frame_id, {"format": "geojson"})
    return JSONResponse(content={"geojson": payload})


@router.post("/import/{frame_id}")
def import_annotations_json(
    frame_id: int,
    body: ImportBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    _require_frame_access(db, current_user, frame_id, request)
    svc = DicomAnnotationService(db)
    try:
        count = svc.import_annotations_from_json(
            frame_id, body.json_data, user_id=current_user.id, replace=body.replace
        )
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit(db, request, current_user, "dicom_annotation.import", frame_id, {"count": count})
    return {"imported": count}


@router.get("/session", response_model=SessionResponse | None)
def get_annotation_session(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    study_uid: str | None = Query(None),
):
    _ensure_enabled()
    session = DicomAnnotationService(db).get_annotation_session(current_user.id, study_uid)
    return session


@router.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def start_annotation_session(
    body: SessionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_enabled()
    _require_instance_access(db, current_user, body.frame_instance_uid, request)
    session = DicomAnnotationService(db).start_session(
        user_id=current_user.id,
        study_uid=body.study_uid,
        series_uid=body.series_uid,
        frame_instance_uid=body.frame_instance_uid,
    )
    _audit(
        db,
        request,
        current_user,
        "dicom_annotation.session_start",
        session.id,
        {"study_uid": body.study_uid},
    )
    return session


@router.get("/config")
def annotation_config(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return {
        "enabled": settings.DICOM_ANNOTATIONS_ENABLED,
        "auto_save_delay_ms": settings.DICOM_ANNOTATIONS_AUTO_SAVE_DELAY_MS,
        "max_per_frame": settings.DICOM_ANNOTATIONS_MAX_PER_FRAME,
        "history_limit": settings.DICOM_ANNOTATIONS_HISTORY_LIMIT,
        "export_max_frames": settings.DICOM_ANNOTATIONS_EXPORT_MAX_FRAMES,
    }
