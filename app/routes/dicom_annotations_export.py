"""DICOM annotation export/import endpoints (Phase 12d)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.routes.dicom_annotation_common import audit_annotation, ensure_annotations_enabled, require_frame_access
from app.services.annotation_export import AnnotationExportService
from app.services.annotation_import import AnnotationImportService
from app.services.dicom_annotations import AnnotationError

router = APIRouter(prefix="/dicom/annotations", tags=["dicom-annotations-export"])


class ExportJsonFilters(BaseModel):
    frame_ids: list[int] = Field(default_factory=list)
    anonymize: bool = False


class ExportPdfOptions(BaseModel):
    frame_id: int
    include_legend: bool = True


class BatchExportBody(BaseModel):
    frame_ids: list[int]
    format: str = "json"
    zip: bool = True


class ImportJsonBody(BaseModel):
    json_data: str
    replace: bool = False


class ImportGeoJsonBody(BaseModel):
    geojson_data: str
    replace: bool = False


@router.get("/export/json/{frame_id}")
def export_json(
    frame_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    anonymize: bool = Query(False),
):
    ensure_annotations_enabled()
    require_frame_access(db, current_user, frame_id, request)
    svc = AnnotationExportService(db)
    payload = svc.export_to_json(frame_id, user=current_user, anonymize=anonymize)
    audit_annotation(db, request, current_user, "dicom_annotation.export", frame_id, {"format": "json"})
    return Response(content=payload, media_type="application/json")


@router.post("/export/json")
def export_json_batch(
    body: ExportJsonFilters,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    results: dict[str, Any] = {}
    svc = AnnotationExportService(db)
    for fid in body.frame_ids:
        require_frame_access(db, current_user, fid, request)
        results[str(fid)] = svc.export_to_json(fid, user=current_user, anonymize=body.anonymize)
    audit_annotation(db, request, current_user, "dicom_annotation.export", None, {"format": "json", "count": len(body.frame_ids)})
    return JSONResponse(content=results)


@router.get("/export/geojson/{frame_id}")
def export_geojson(
    frame_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    require_frame_access(db, current_user, frame_id, request)
    svc = AnnotationExportService(db)
    payload = svc.export_to_geojson(frame_id)
    audit_annotation(db, request, current_user, "dicom_annotation.export", frame_id, {"format": "geojson"})
    return Response(content=payload, media_type="application/geo+json")


@router.get("/export/pdf/{frame_id}")
def export_pdf(
    frame_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    require_frame_access(db, current_user, frame_id, request)
    svc = AnnotationExportService(db)
    try:
        pdf_bytes = svc.export_to_pdf(frame_id, user=current_user)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.export", frame_id, {"format": "pdf"})
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="annotations_frame_{frame_id}.pdf"'},
    )


@router.post("/export/pdf")
def export_pdf_with_options(
    body: ExportPdfOptions,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    require_frame_access(db, current_user, body.frame_id, request)
    svc = AnnotationExportService(db)
    try:
        pdf_bytes = svc.export_to_pdf(
            body.frame_id,
            user=current_user,
            options={"include_legend": body.include_legend},
        )
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.export", body.frame_id, {"format": "pdf"})
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="annotations_frame_{body.frame_id}.pdf"'},
    )


@router.post("/export/batch")
def export_batch(
    body: BatchExportBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    for fid in body.frame_ids:
        require_frame_access(db, current_user, fid, request)
    svc = AnnotationExportService(db)
    try:
        data = svc.export_batch(body.frame_ids, body.format, user=current_user)
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(
        db,
        request,
        current_user,
        "dicom_annotation.export_batch",
        None,
        {"format": body.format, "count": len(body.frame_ids)},
    )
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="annotations_export.zip"'},
    )


@router.post("/import/geojson/{frame_id}")
def import_geojson(
    frame_id: int,
    body: ImportGeoJsonBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ensure_annotations_enabled()
    require_frame_access(db, current_user, frame_id, request)
    svc = AnnotationImportService(db)
    try:
        count = svc.import_from_geojson(
            frame_id, body.geojson_data, user_id=current_user.id, replace=body.replace
        )
    except AnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_annotation(db, request, current_user, "dicom_annotation.import", frame_id, {"format": "geojson", "count": count})
    return {"imported": count}
