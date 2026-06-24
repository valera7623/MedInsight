import logging

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "medinsight",
    broker=settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.parse_task",
        "app.tasks.predict_task",
        "app.tasks.learn_task",
        "app.tasks.webhook_task",
        "app.tasks.export_task",
        "app.tasks.backup_task",
        "app.tasks.dicom_task",
        "app.tasks.dicom_zip_task",
        "app.tasks.dicom_volume_task",
        "app.tasks.audit_export_task",
        "app.tasks.audit_sync_task",
    ],
)


def _crontab_from_cron(expr: str):
    """Build a celery crontab from a 5-field cron string 'm h dom mon dow'."""
    from celery.schedules import crontab

    parts = (expr or "").split()
    if len(parts) != 5:
        return crontab(minute=0, hour=2)  # safe default: daily 02:00
    minute, hour, dom, mon, dow = parts
    return crontab(minute=minute, hour=hour, day_of_month=dom, month_of_year=mon, day_of_week=dow)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_max_retries=1,
    broker_connection_retry_on_startup=False,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
)

celery_app.conf.beat_schedule = {}

if settings.SELF_HEALING_ENABLED:
    celery_app.conf.beat_schedule["learn-from-failures-every-6h"] = {
        "task": "app.tasks.learn_task.learn_from_failures",
        "schedule": 6 * 60 * 60.0,  # every 6 hours
    }

if settings.BACKUP_ENABLED:
    celery_app.conf.beat_schedule.update({
        "backup-full-daily": {
            "task": "app.tasks.backup_task.scheduled_full_backup",
            "schedule": _crontab_from_cron(settings.BACKUP_SCHEDULE_FULL),
        },
        "backup-db-hourly": {
            "task": "app.tasks.backup_task.scheduled_db_backup",
            "schedule": _crontab_from_cron(settings.BACKUP_SCHEDULE_DB),
        },
        "backup-cleanup-daily": {
            "task": "app.tasks.backup_task.backup_cleanup",
            "schedule": _crontab_from_cron(settings.BACKUP_SCHEDULE_CLEANUP),
        },
    })

if settings.SIEM_EXPORT_ENABLED:
    celery_app.conf.beat_schedule["sync-pending-audit-events"] = {
        "task": "app.tasks.audit_sync_task.sync_pending_audit_events",
        "schedule": 5 * 60.0,  # every 5 minutes
    }


if settings.OTEL_ENABLED:
    try:
        from app.telemetry.setup import setup_telemetry
        from app.telemetry.celery import instrument_celery

        setup_telemetry()
        instrument_celery()
    except Exception:  # noqa: BLE001 — tracing is optional
        pass


def redis_available() -> bool:
    """Fast check whether the Redis broker is reachable.

    Avoids long broker-connection timeouts in request handlers when Redis is
    down, so endpoints can fall back to synchronous processing immediately.
    """
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return True
    except Exception:
        return False
