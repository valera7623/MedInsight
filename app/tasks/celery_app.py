import logging

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "medinsight",
    broker=settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.parse_task", "app.tasks.predict_task"],
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
)

celery_app.conf.beat_schedule = {}
