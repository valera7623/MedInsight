"""Celery task: archive expired audit logs."""

from app.database import SessionLocal
from app.services.audit_retention import archive_expired_audit_logs
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.audit_retention_task.archive_audit_logs")
def archive_audit_logs() -> int:
    db = SessionLocal()
    try:
        return archive_expired_audit_logs(db)
    finally:
        db.close()
