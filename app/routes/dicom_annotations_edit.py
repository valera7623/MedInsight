"""DICOM annotation editing endpoints (Phase 12d)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.routes.dicom_annotation_common import audit_annotation, ensure_annotations_enabled, require_frame_access
from app.services.dicom_annotations import AnnotationError, DicomAnnotationService

router = APIRouter(prefix="/dicom/annotations", tags=["dicom-annotations-edit"])


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


class MoveBody(BaseModel):
    coordinates: dict[str, Any]


class ResizeBody(BaseModel):
    coordinates: dict[str, Any]


class ColorBody(BaseModel):
    color: str = Field(..., max_length=16)


class LabelBody(BaseModel):
    label: str | None = Field(None, max_length=255)


class TypeBody(BaseModel):
    type: str = Field(..., max_length=32)


def _get_ann_or_404(svc: DicomAnnotationService, annotation_id: int, request: Request, user: User, db: Session):
    ann = svc.get_annotation(annotation_id)
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    require_frame_access(db, user, ann.frame_id, request)
    return ann


@router.put("/{annotation_id}/move", response_model=AnnotationResponse)
def move_annotation(
    annotation_id: int,
    body: MoveBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    svc = DicomAnnotationService(db)
    _get_ann_or_404(svc, annotation_id, request, current_user, db)
    try:
        updated = svc.move_annotation(annotation_id, body.coordinates, user_id=current_user.id)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.move", annotation_id)
    return updated


@router.put("/{annotation_id}/resize", response_model=AnnotationResponse)
def resize_annotation(
    annotation_id: int,
    body: ResizeBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    svc = DicomAnnotationService(db)
    _get_ann_or_404(svc, annotation_id, request, current_user, db)
    try:
        updated = svc.resize_annotation(annotation_id, body.coordinates, user_id=current_user.id)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.resize", annotation_id)
    return updated


@router.put("/{annotation_id}/color", response_model=AnnotationResponse)
def change_annotation_color(
    annotation_id: int,
    body: ColorBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    svc = DicomAnnotationService(db)
    _get_ann_or_404(svc, annotation_id, request, current_user, db)
    try:
        updated = svc.update_color(annotation_id, body.color, user_id=current_user.id)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.color", annotation_id)
    return updated


@router.put("/{annotation_id}/label", response_model=AnnotationResponse)
def change_annotation_label(
    annotation_id: int,
    body: LabelBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    svc = DicomAnnotationService(db)
    _get_ann_or_404(svc, annotation_id, request, current_user, db)
    try:
        updated = svc.update_label(annotation_id, body.label, user_id=current_user.id)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.label", annotation_id)
    return updated


@router.put("/{annotation_id}/type", response_model=AnnotationResponse)
def change_annotation_type(
    annotation_id: int,
    body: TypeBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    svc = DicomAnnotationService(db)
    _get_ann_or_404(svc, annotation_id, request, current_user, db)
    try:
        updated = svc.update_type(annotation_id, body.type, user_id=current_user.id)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.type", annotation_id)
    return updated
