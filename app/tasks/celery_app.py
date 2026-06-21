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
    ],
)

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

if settings.SELF_HEALING_ENABLED:
    celery_app.conf.beat_schedule = {
        "learn-from-failures-every-6h": {
            "task": "app.tasks.learn_task.learn_from_failures",
            "schedule": 6 * 60 * 60.0,  # every 6 hours
        },
    }
else:
    celery_app.conf.beat_schedule = {}


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
