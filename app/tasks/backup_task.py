"""Celery tasks for scheduled & on-demand backups (Phase 8)."""

from __future__ import annotations

import logging

from app.config import settings
from app.services.backup import get_backup_service, send_alert
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.backup_task.scheduled_full_backup")
def scheduled_full_backup() -> dict:
    return get_backup_service().backup_full()


@celery_app.task(name="app.tasks.backup_task.scheduled_db_backup")
def scheduled_db_backup() -> dict:
    path = get_backup_service().backup_database()
    return {"status": "completed", "path": path}


@celery_app.task(name="app.tasks.backup_task.scheduled_storage_backup")
def scheduled_storage_backup() -> dict:
    path = get_backup_service().backup_storage()
    return {"status": "completed", "path": path}


@celery_app.task(bind=True, name="app.tasks.backup_task.create_backup")
def create_backup(self, backup_type: str) -> dict:
    """On-demand backup triggered from the admin API."""
    svc = get_backup_service()
    backup_id = None
    if backup_type == "full":
        result = svc.backup_full(backup_id)
        return {"status": "completed", **result}
    if backup_type == "db":
        return {"status": "completed", "path": svc.backup_database(backup_id)}
    if backup_type == "storage":
        return {"status": "completed", "path": svc.backup_storage(backup_id)}
    return {"status": "failed", "error": f"Unknown backup type: {backup_type}"}


@celery_app.task(bind=True, name="app.tasks.backup_task.restore_task")
def restore_task(self, backup_path: str, restore_type: str) -> dict:
    try:
        get_backup_service().restore_from_backup(backup_path, restore_type)
        return {"status": "completed", "type": restore_type}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Restore task failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


@celery_app.task(name="app.tasks.backup_task.backup_cleanup")
def backup_cleanup() -> dict:
    svc = get_backup_service()
    removed = svc.cleanup_old_backups()

    # Health alert: warn if the newest backup is too old.
    age = svc.latest_backup_age_hours()
    if age is None:
        send_alert("No backups found at all")
    elif age > settings.BACKUP_ALERT_MAX_AGE_HOURS:
        send_alert(f"Latest backup is {age:.0f}h old (> {settings.BACKUP_ALERT_MAX_AGE_HOURS}h)")
    return {"removed": removed, "latest_age_hours": age}
