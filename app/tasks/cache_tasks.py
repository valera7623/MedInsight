"""Celery tasks for static cache maintenance."""

from __future__ import annotations

import logging

from app.config import settings
from app.database import SessionLocal
from app.services.cache_manager import CacheManager
from app.services.static_cache import StaticCache
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.cache_tasks.cleanup_static_cache")
def cleanup_static_cache() -> dict:
    """Daily cleanup of aged / oversized static DOCX cache."""
    if not settings.STATIC_CACHE_ENABLED:
        return {"status": "skipped", "reason": "static cache disabled"}

    static = StaticCache()
    removed_old = static.cleanup_old(settings.STATIC_CACHE_RETENTION_DAYS)
    removed_size = static.cleanup_by_size(settings.STATIC_CACHE_MAX_SIZE_MB)
    stats = static.get_cache_stats()
    result = {
        "status": "completed",
        "removed_old": removed_old,
        "removed_size": removed_size,
        "file_count": stats["file_count"],
        "total_size_mb": stats["total_size_mb"],
    }
    logger.info("Static cache cleanup: %s", result)
    return result


@celery_app.task(name="app.tasks.cache_tasks.warmup_cache")
def warmup_cache(patient_ids: list[int] | None = None) -> dict:
    """Pre-generate DOCX cards into Redis + static cache."""
    db = SessionLocal()
    try:
        mgr = CacheManager(db)
        ids = list(patient_ids or [])
        if not ids:
            from app.models import Patient

            ids = [p.id for p in db.query(Patient).limit(50).all()]
        import asyncio

        warmed = asyncio.run(mgr.warmup(ids))
        return {"status": "completed", "warmed": warmed, "patient_ids": ids}
    finally:
        db.close()
