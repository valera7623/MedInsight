"""Shared helpers for DICOM annotation route modules."""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.middleware.tenant import get_request_tenant_id
from app.models import DicomFrame, User
from app.services.access import can_view_patient, effective_tenant_id, require_tenant_access
from app.services.audit import log_audit
from app.services.dicom_annotations import get_frame_by_instance_uid, get_frame_with_study


def ensure_annotations_enabled() -> None:
    if not settings.DICOM_ANNOTATIONS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DICOM annotations are disabled",
        )


def audit_annotation(
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


def require_frame_access(db: Session, user: User, frame_id: int, request: Request) -> DicomFrame:
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
