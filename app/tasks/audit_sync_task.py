"""Periodic Celery task: sync pending audit events to SIEM."""

from __future__ import annotations

import logging

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog
from app.services.audit_exporter import AuditExporter
from app.services.siem_target_manager import SiemTargetManager
from app.tasks.audit_export_task import export_audit_batch
from app.tasks.celery_app import celery_app, redis_available

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.audit_sync_task.sync_pending_audit_events")
def sync_pending_audit_events() -> int:
    """Export pending audit events to the configured SIEM target."""
    if not settings.SIEM_EXPORT_ENABLED:
        return 0

    db = SessionLocal()
    try:
        pending_ids = (
            db.query(AuditLog.id)
            .filter(AuditLog.export_status == "pending")
            .order_by(AuditLog.id.asc())
            .limit(settings.SIEM_EXPORT_BATCH_SIZE)
            .all()
        )
        event_ids = [row[0] for row in pending_ids]
        if not event_ids:
            return 0

        target = SiemTargetManager.get_default_target()
        fmt = target.get("format", settings.SIEM_EXPORT_PROTOCOL)

        if redis_available():
            export_audit_batch.delay(event_ids, fmt, target)
            logger.info("Enqueued %d pending audit events for SIEM export", len(event_ids))
            return len(event_ids)

        exporter = AuditExporter(db)
        try:
            events = db.query(AuditLog).filter(AuditLog.id.in_(event_ids)).all()
            ok = exporter.export_batch(events, fmt, target)
            logger.info("Synced %d audit events (success=%s)", len(events), ok)
            return len(events)
        finally:
            exporter.close()
    except Exception as exc:
        logger.exception("sync_pending_audit_events failed: %s", exc)
        return 0
    finally:
        db.close()
