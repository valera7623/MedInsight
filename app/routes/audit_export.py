"""Admin API for SIEM audit export management."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import AuditExportLog, AuditLog, User
from app.services.audit_exporter import AuditExporter
from app.services.siem_target_manager import SiemTargetManager
from app.tasks.audit_export_task import export_audit_batch
from app.tasks.celery_app import redis_available

router = APIRouter(prefix="/admin/audit/export", tags=["audit-export"])


class ExportRetryRequest(BaseModel):
    event_ids: list[int] | None = None
    target: str | None = None


class ExportTestRequest(BaseModel):
    target: str | None = None
    format: str | None = Field(None, pattern=r"^(syslog|cef|splunk_hec|jsonl)$")


def _event_dump(row: AuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "action": row.action,
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "export_status": row.export_status,
        "export_attempts": row.export_attempts,
        "last_export_attempt_at": row.last_export_attempt_at,
        "export_error": row.export_error,
        "signature": row.signature,
        "signed_at": row.signed_at,
        "created_at": row.created_at,
    }


@router.get("/status")
def export_status(
    current_user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    targets = SiemTargetManager.get_targets()
    default = SiemTargetManager.get_default_target() if settings.SIEM_EXPORT_ENABLED else None
    return {
        "enabled": settings.SIEM_EXPORT_ENABLED,
        "signing_enabled": settings.AUDIT_SIGNING_ENABLED,
        "protocol": settings.SIEM_EXPORT_PROTOCOL,
        "batch_size": settings.SIEM_EXPORT_BATCH_SIZE,
        "retry_count": settings.SIEM_EXPORT_RETRY_COUNT,
        "redis_available": redis_available(),
        "default_target": default,
        "targets": targets,
    }


@router.post("/retry")
def export_retry(
    body: ExportRetryRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    if not settings.SIEM_EXPORT_ENABLED:
        raise HTTPException(status_code=400, detail="SIEM export is disabled")

    target_name = body.target
    target = SiemTargetManager.get_target(target_name) if target_name else SiemTargetManager.get_default_target()
    fmt = target.get("format", settings.SIEM_EXPORT_PROTOCOL)

    if body.event_ids:
        event_ids = body.event_ids
    else:
        exporter = AuditExporter(db)
        try:
            count = exporter.retry_failed_events()
            return {"status": "retried", "count": count, "mode": "failed_events"}
        finally:
            exporter.close()

    if redis_available():
        task_id = export_audit_batch.delay(event_ids, fmt, target).id
        return {"status": "enqueued", "task_id": task_id, "count": len(event_ids)}

    events = db.query(AuditLog).filter(AuditLog.id.in_(event_ids)).all()
    exporter = AuditExporter(db)
    try:
        ok = exporter.export_batch(events, fmt, target)
        return {"status": "exported" if ok else "failed", "count": len(events)}
    finally:
        exporter.close()


@router.post("/test")
def export_test(
    body: ExportTestRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    target_name = body.target or "sentinel"
    try:
        target = SiemTargetManager.get_target(target_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    fmt = body.format or target.get("format", settings.SIEM_EXPORT_PROTOCOL)
    connected = SiemTargetManager.test_connection(target)

    test_event = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="audit.export.test",
        resource_type="siem",
        details={"test": True, "target": target_name, "format": fmt},
        export_status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(test_event)
    db.flush()
    from app.services.audit_signer import AuditSigner

    data = {
        "id": test_event.id,
        "user_id": test_event.user_id,
        "tenant_id": test_event.tenant_id,
        "action": test_event.action,
        "resource_type": test_event.resource_type,
        "resource_id": test_event.resource_id,
        "ip_address": None,
        "user_agent": None,
        "details": test_event.details,
        "created_at": test_event.created_at,
    }
    test_event.signature = AuditSigner.sign_event(data)
    test_event.signed_at = datetime.utcnow()
    db.commit()

    exporter = AuditExporter(db)
    try:
        sent = exporter.export_batch([test_event], fmt, target)
        return {
            "connection_ok": connected,
            "export_ok": sent,
            "event_id": test_event.id,
            "target": target_name,
            "format": fmt,
        }
    finally:
        exporter.close()


@router.get("/events")
def list_exported_events(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    status: str | None = Query(None, pattern=r"^(pending|exported|failed)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = db.query(AuditLog).order_by(AuditLog.id.desc())
    if status:
        query = query.filter(AuditLog.export_status == status)
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return {"total": total, "items": [_event_dump(r) for r in rows]}


@router.get("/stats")
def export_stats(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    by_status = dict(
        db.query(AuditLog.export_status, func.count(AuditLog.id))
        .group_by(AuditLog.export_status)
        .all()
    )
    export_log_stats = dict(
        db.query(AuditExportLog.status, func.count(AuditExportLog.id))
        .group_by(AuditExportLog.status)
        .all()
    )
    by_target = dict(
        db.query(AuditExportLog.target, func.count(AuditExportLog.id))
        .group_by(AuditExportLog.target)
        .all()
    )
    last_export = db.query(func.max(AuditExportLog.created_at)).scalar()
    return {
        "events_by_status": by_status,
        "export_logs_by_status": export_log_stats,
        "exports_by_target": by_target,
        "last_export_at": last_export,
        "signing_enabled": settings.AUDIT_SIGNING_ENABLED,
        "export_enabled": settings.SIEM_EXPORT_ENABLED,
    }
