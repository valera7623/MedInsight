"""Backup & restore admin endpoints (super_admin only) — Phase 8."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_super_admin
from app.database import get_db
from app.models import User
from app.services.audit import log_audit
from app.services.backup import get_backup_service
from app.tasks.celery_app import redis_available

router = APIRouter(prefix="/admin/backup", tags=["admin-backup"])

BackupType = Literal["full", "db", "storage"]


class CreateBackupRequest(BaseModel):
    type: BackupType = "full"


class RestoreRequest(BaseModel):
    backup_id: str
    type: BackupType = "full"
    confirm: bool = False


def _audit(db: Session, user: User, request: Request, action: str, detail: dict) -> None:
    log_audit(
        db,
        user_id=user.id,
        tenant_id=user.tenant_id,
        action=action,
        resource_type="backup",
        resource_id=None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=detail,
    )


@router.post("/create")
def create_backup(
    body: CreateBackupRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_super_admin)],
):
    _audit(db, current_user, request, "backup_create", {"type": body.type})

    if redis_available():
        from app.tasks.backup_task import create_backup as create_backup_task

        task = create_backup_task.delay(body.type)
        return {"job_id": task.id, "status": "pending", "type": body.type}

    # Synchronous fallback when Celery/Redis is unavailable.
    svc = get_backup_service()
    if body.type == "full":
        result = svc.backup_full()
        return {"job_id": result["backup_id"], "status": "completed", "type": "full", **result}
    path = svc.backup_database() if body.type == "db" else svc.backup_storage()
    return {"job_id": None, "status": "completed", "type": body.type, "path": path}


@router.get("/status/{job_id}")
def backup_status(
    job_id: str,
    current_user: Annotated[User, Depends(require_super_admin)],
):
    from celery.result import AsyncResult

    from app.tasks.celery_app import celery_app

    res = AsyncResult(job_id, app=celery_app)
    if res.successful():
        result = res.result or {}
        return {
            "status": "completed",
            "backup_path": result.get("path"),
            "size": result.get("size"),
            "duration": result.get("duration"),
            "result": result,
        }
    if res.failed():
        return {"status": "failed", "error": str(res.result)}
    return {"status": res.state.lower() if res.state else "pending"}


@router.get("/list")
def list_backups(current_user: Annotated[User, Depends(require_super_admin)]):
    return {"backups": get_backup_service().list_backups()}


@router.get("/download/{backup_id}")
def download_backup(
    backup_id: str,
    current_user: Annotated[User, Depends(require_super_admin)],
    type: BackupType | None = None,
):
    svc = get_backup_service()
    path = svc._find_backup_path(backup_id, type)
    if path is None or not Path(path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return FileResponse(path=str(path), media_type="application/gzip", filename=Path(path).name)


@router.post("/restore")
def restore_backup(
    body: RestoreRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_super_admin)],
):
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restore requires confirm=true (destructive operation)",
        )
    svc = get_backup_service()
    path = svc._find_backup_path(body.backup_id, body.type)
    if path is None or not Path(path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")

    _audit(db, current_user, request, "backup_restore", {"backup_id": body.backup_id, "type": body.type})

    if redis_available():
        from app.tasks.backup_task import restore_task

        task = restore_task.delay(str(path), body.type)
        return {"status": "restore_started", "job_id": task.id}

    # Synchronous fallback.
    svc.restore_from_backup(str(path), body.type)
    return {"status": "restore_completed", "job_id": None}


@router.delete("/{backup_id}")
def delete_backup(
    backup_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_super_admin)],
):
    svc = get_backup_service()
    matches = [b for b in svc.list_backups() if b["id"] == backup_id]
    if not matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    for b in matches:
        Path(b["path"]).unlink(missing_ok=True)
        (svc.base / "metadata" / f"{backup_id}.json").unlink(missing_ok=True)
    _audit(db, current_user, request, "backup_delete", {"backup_id": backup_id})
    return {"status": "deleted", "removed": len(matches)}
