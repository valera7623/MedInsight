"""Celery task: export a batch of audit events to SIEM."""

from __future__ import annotations

import logging
from datetime import datetime

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog
from app.services.audit_exporter import AuditExporter
from app.services.siem_target_manager import SiemTargetManager
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.audit_export_task.export_audit_batch",
    max_retries=settings.SIEM_EXPORT_RETRY_COUNT,
    default_retry_delay=30,
)
def export_audit_batch(self, event_ids: list[int], fmt: str, target: dict) -> dict:
    if not settings.SIEM_EXPORT_ENABLED:
        return {"status": "skipped", "reason": "SIEM_EXPORT_ENABLED=false"}

    db = SessionLocal()
    exporter = AuditExporter(db)
    try:
        events = db.query(AuditLog).filter(AuditLog.id.in_(event_ids)).all()
        if not events:
            return {"status": "empty", "count": 0}

        ok = exporter.export_batch(events, fmt, target)
        return {
            "status": "exported" if ok else "failed",
            "count": len(events),
            "format": fmt,
            "target": target.get("name"),
        }
    except Exception as exc:
        logger.exception("Audit export batch failed: %s", exc)
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
    finally:
        exporter.close()
        db.close()


def enqueue_pending_batch(event_ids: list[int] | None = None) -> str | None:
    """Enqueue export for pending events; returns Celery task id or None."""
    from app.tasks.celery_app import redis_available

    if not settings.SIEM_EXPORT_ENABLED or not redis_available():
        return None
    db = SessionLocal()
    try:
        if event_ids is None:
            rows = (
                db.query(AuditLog.id)
                .filter(AuditLog.export_status == "pending")
                .order_by(AuditLog.id.asc())
                .limit(settings.SIEM_EXPORT_BATCH_SIZE)
                .all()
            )
            event_ids = [r[0] for r in rows]
        if not event_ids:
            return None
        target = SiemTargetManager.get_default_target()
        fmt = target.get("format", settings.SIEM_EXPORT_PROTOCOL)
        result = export_audit_batch.delay(event_ids, fmt, target)
        return result.id
    finally:
        db.close()
