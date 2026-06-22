"""3D volume rendering API — MPR slices, volume projection, reconstruction."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import User
from app.routes.dicom import _get_study_or_404
from app.services.audit import log_audit
from app.services.dicom_volume import DicomVolumeError, DicomVolumeService
from app.tasks.celery_app import redis_available
from app.tasks.dicom_volume_task import build_volume_from_study

router = APIRouter(prefix="/dicom/volume", tags=["dicom-3d"])
logger = logging.getLogger(__name__)


class VolumeReconstructResponse(BaseModel):
    study_uid: str
    job_id: str | None = None
    status: str
    message: str | None = None


class VolumeInfoResponse(BaseModel):
    study_uid: str
    series_uid: str | None = None
    modality: str | None = None
    num_slices: int = 0
    dimensions: list[int] = Field(default_factory=list)
    spacing: list[float] = Field(default_factory=list)
    orientation: list[float] = Field(default_factory=list)
    cached: bool = False
    status: str = "not_built"
    presets: list[str] = Field(default_factory=list)
    warning: str | None = None
    available_series: list[dict[str, Any]] = Field(default_factory=list)


def _ensure_3d_enabled() -> None:
    if not settings.DICOM_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DICOM support is disabled")
    if not settings.DICOM_3D_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DICOM 3D rendering is disabled")


def _render_params(
    *,
    window_center: float | None = None,
    window_width: float | None = None,
    preset: str | None = None,
    mode: str | None = None,
    azimuth: float = 0,
    elevation: float = 0,
) -> dict[str, Any]:
    params: dict[str, Any] = {"azimuth": azimuth, "elevation": elevation}
    if window_center is not None:
        params["window_center"] = window_center
    if window_width is not None:
        params["window_width"] = window_width
    if preset:
        params["preset"] = preset
    if mode:
        params["mode"] = mode
    return params


class VolumePreviewResponse(BaseModel):
    study_uid: str
    info: dict[str, Any] = Field(default_factory=dict)
    slices: dict[str, int] = Field(default_factory=dict)
    render: str
    mpr: dict[str, str] = Field(default_factory=dict)
    warning: str | None = None


@router.get("/{study_uid}/preview", response_model=VolumePreviewResponse)
def render_volume_preview(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    window_center: float | None = Query(None),
    window_width: float | None = Query(None),
    preset: str | None = Query(None),
    mode: str = Query("mip", pattern="^(mip|minip|avg|vr)$"),
    azimuth: float = Query(0, ge=-180, le=180),
    elevation: float = Query(0, ge=-90, le=90),
    axial_slice: int | None = Query(None, ge=0),
    coronal_slice: int | None = Query(None, ge=0),
    sagittal_slice: int | None = Query(None, ge=0),
):
    """Single-request bootstrap: VR + axial/coronal/sagittal MPR (base64 PNG)."""
    _ensure_3d_enabled()
    _get_study_or_404(db, study_uid, current_user, request)
    service = DicomVolumeService(db)
    params = _render_params(
        window_center=window_center,
        window_width=window_width,
        preset=preset,
        mode=mode,
        azimuth=azimuth,
        elevation=elevation,
    )
    slice_map: dict[str, int] = {}
    if axial_slice is not None:
        slice_map["axial"] = axial_slice
    if coronal_slice is not None:
        slice_map["coronal"] = coronal_slice
    if sagittal_slice is not None:
        slice_map["sagittal"] = sagittal_slice
    try:
        payload = service.render_preview(study_uid, slices=slice_map or None, params=params)
    except DicomVolumeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return VolumePreviewResponse(
        study_uid=payload["study_uid"],
        info=payload.get("info", {}),
        slices=payload.get("slices", {}),
        render=payload["render"],
        mpr=payload.get("mpr", {}),
        warning=payload.get("info", {}).get("warning"),
    )


@router.get("/{study_uid}/info", response_model=VolumeInfoResponse)
def get_volume_info(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_3d_enabled()
    _get_study_or_404(db, study_uid, current_user, request)
    service = DicomVolumeService(db)
    try:
        info = service.get_volume_info(study_uid)
    except DicomVolumeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return VolumeInfoResponse(**info)


@router.get("/{study_uid}/render")
def render_volume(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    window_center: float | None = Query(None),
    window_width: float | None = Query(None),
    preset: str | None = Query(None),
    mode: str = Query("mip", pattern="^(mip|minip|avg|vr)$"),
    azimuth: float = Query(0, ge=-180, le=180),
    elevation: float = Query(0, ge=-90, le=90),
):
    _ensure_3d_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)
    service = DicomVolumeService(db)
    params = _render_params(
        window_center=window_center,
        window_width=window_width,
        preset=preset,
        mode=mode,
        azimuth=azimuth,
        elevation=elevation,
    )
    try:
        png = service.render_volume(study_uid, params)
    except DicomVolumeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=study.tenant_id,
        action="view",
        resource_type="dicom_volume_3d",
        resource_id=study.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"study_uid": study_uid, "mode": mode},
    )

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/{study_uid}/mpr/{plane}/{slice_index}")
def render_mpr_slice(
    study_uid: str,
    plane: str,
    slice_index: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    window_center: float | None = Query(None),
    window_width: float | None = Query(None),
    preset: str | None = Query(None),
):
    _ensure_3d_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)
    if plane.lower() not in {"axial", "coronal", "sagittal"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plane")

    service = DicomVolumeService(db)
    params = _render_params(window_center=window_center, window_width=window_width, preset=preset)
    try:
        png = service.render_mpr(study_uid, plane, slice_index, params)
    except DicomVolumeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=study.tenant_id,
        action="view",
        resource_type="dicom_volume_mpr",
        resource_id=study.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"study_uid": study_uid, "plane": plane, "slice": slice_index},
    )

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.post("/{study_uid}/reconstruct", response_model=VolumeReconstructResponse)
def reconstruct_volume(
    study_uid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _ensure_3d_enabled()
    study = _get_study_or_404(db, study_uid, current_user, request)
    if study.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Study is not ready (status={study.status})",
        )

    service = DicomVolumeService(db)
    if service.is_volume_cached(study_uid):
        return VolumeReconstructResponse(
            study_uid=study_uid,
            status="ready",
            message="Volume already cached",
        )

    try:
        meta = service.get_volume_info(study_uid)
    except DicomVolumeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    num_slices = int(meta.get("num_slices") or 0)
    if num_slices <= settings.DICOM_3D_SYNC_BUILD_MAX_SLICES:
        try:
            service.build_volume_from_frames(study_uid)
        except DicomVolumeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return VolumeReconstructResponse(
            study_uid=study_uid,
            status="ready",
            message="Volume reconstructed synchronously",
        )

    if redis_available():
        try:
            task = build_volume_from_study.delay(study_uid)
            log_audit(
                db,
                user_id=current_user.id,
                tenant_id=study.tenant_id,
                action="reconstruct",
                resource_type="dicom_volume",
                resource_id=study.id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                details={"study_uid": study_uid, "async": True},
            )
            return VolumeReconstructResponse(
                study_uid=study_uid,
                job_id=task.id,
                status="processing",
                message="Volume reconstruction started",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Celery volume task failed, sync fallback: %s", exc)

    try:
        service.build_volume_from_frames(study_uid)
    except DicomVolumeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=study.tenant_id,
        action="reconstruct",
        resource_type="dicom_volume",
        resource_id=study.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"study_uid": study_uid, "async": False},
    )

    return VolumeReconstructResponse(
        study_uid=study_uid,
        status="ready",
        message="Volume reconstructed synchronously",
    )
