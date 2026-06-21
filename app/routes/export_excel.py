"""Excel export endpoints (sync for small datasets, Celery for large ones)."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import User
from app.services.access import can_export, effective_tenant_id
from app.services.excel_export import ExcelExporter, available_columns
from app.services.export_data import collect_export_rows, count_export_rows
from app.tasks.celery_app import redis_available

router = APIRouter(prefix="/export", tags=["export"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_EXPORTER_METHODS = {
    "patients": "export_patients",
    "documents": "export_documents",
    "predictions": "export_predictions",
    "users": "export_users",
    "audit": "export_audit",
}


class ExportRequest(BaseModel):
    filters: dict = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)


def _validate_columns(entity: str, columns: list[str]) -> list[str]:
    if len(columns) > settings.EXPORT_MAX_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many columns (max {settings.EXPORT_MAX_COLUMNS})",
        )
    valid = set(available_columns(entity))
    unknown = [c for c in columns if c not in valid]
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown columns: {unknown}")
    return columns


def _run_export(
    entity: str,
    body: ExportRequest,
    request: Request,
    db: Session,
    user: User,
):
    columns = _validate_columns(entity, body.columns)
    tenant_id = effective_tenant_id(user, get_request_tenant_id(request))

    total = count_export_rows(db, entity, user, tenant_id, body.filters)

    # Large datasets -> async via Celery (if broker is available).
    if total > settings.EXPORT_MAX_ROWS and redis_available():
        from app.tasks.export_task import generate_export

        task = generate_export.delay(entity, user.id, tenant_id, body.filters, columns)
        return {
            "status": "processing",
            "job_id": task.id,
            "rows": total,
            "download_url": f"/api/export/download/{task.id}",
            "message": f"Экспорт {total} строк выполняется асинхронно. Скачайте по download_url, когда будет готов.",
        }

    rows = collect_export_rows(db, entity, user, tenant_id, body.filters, settings.EXPORT_MAX_ROWS)
    exporter = ExcelExporter()
    buffer: io.BytesIO = getattr(exporter, _EXPORTER_METHODS[entity])(rows, columns or None)

    filename = f"{entity}_export_{datetime.utcnow():%Y-%m-%d}.xlsx"
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/patients")
def export_patients(
    body: ExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")
    return _run_export("patients", body, request, db, current_user)


@router.post("/documents")
def export_documents(
    body: ExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")
    return _run_export("documents", body, request, db, current_user)


@router.post("/predictions")
def export_predictions(
    body: ExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")
    return _run_export("predictions", body, request, db, current_user)


@router.post("/users")
def export_users(
    body: ExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    return _run_export("users", body, request, db, current_user)


@router.post("/audit")
def export_audit(
    body: ExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    return _run_export("audit", body, request, db, current_user)


@router.get("/download/{job_id}")
def download_export(
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    # job_id is a Celery UUID; reject anything that could escape the export dir.
    safe_id = Path(job_id).name
    export_dir = Path(settings.EXPORT_TEMP_DIR)
    matches = list(export_dir.glob(f"*_export_{safe_id}.xlsx")) if export_dir.exists() else []
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл ещё не готов или не найден. Повторите попытку позже.",
        )
    file_path = matches[0]
    return FileResponse(
        path=str(file_path),
        media_type=XLSX_MEDIA,
        filename=file_path.name,
    )
