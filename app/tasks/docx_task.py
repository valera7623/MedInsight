"""Asynchronous DOCX generation for patient cards with Redis cache."""

from __future__ import annotations

import logging
from io import BytesIO

from app.config import settings
from app.core.cache import cache_service, docx_cache_key, docx_path_cache_key
from app.database import SessionLocal
from app.services.cache_invalidation import get_cache_version
from app.services.docx_generator import DocxGenerator, save_docx_to_patient_reports
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _load_cached_docx(patient_id: int, options: dict, db) -> tuple[BytesIO | None, str | None]:
    version = get_cache_version(db, f"patient:{patient_id}")
    key = docx_cache_key(patient_id, options, version)
    path_key = docx_path_cache_key(patient_id, options, version)

    cached_bytes = cache_service.get_bytes_sync(key)
    if cached_bytes:
        logger.info("DOCX cache HIT (redis) patient=%s key=%s", patient_id, key)
        cached_path = cache_service.get_bytes_sync(path_key)
        path_str = cached_path.decode("utf-8") if cached_path else None
        buffer = BytesIO(cached_bytes)
        buffer.seek(0)
        return buffer, path_str

    cached_path = cache_service.get_bytes_sync(path_key)
    if cached_path:
        from pathlib import Path

        path = Path(cached_path.decode("utf-8"))
        if path.exists():
            logger.info("DOCX cache HIT (filesystem) patient=%s path=%s", patient_id, path)
            data = path.read_bytes()
            cache_service.set_bytes_sync(key, data, settings.REDIS_CACHE_DOCX_TTL)
            buffer = BytesIO(data)
            buffer.seek(0)
            return buffer, str(path)

    return None, None


def _store_docx_cache(patient_id: int, options: dict, buffer: BytesIO, file_path: str, db) -> None:
    version = get_cache_version(db, f"patient:{patient_id}")
    key = docx_cache_key(patient_id, options, version)
    path_key = docx_path_cache_key(patient_id, options, version)
    data = buffer.getvalue()
    cache_service.set_bytes_sync(key, data, settings.REDIS_CACHE_DOCX_TTL)
    cache_service.set_bytes_sync(path_key, file_path.encode("utf-8"), settings.REDIS_CACHE_DOCX_TTL)
    logger.info("DOCX cached patient=%s key=%s size=%d", patient_id, key, len(data))


@celery_app.task(bind=True, name="app.tasks.docx_task.generate_patient_card_async")
def generate_patient_card_async(
    self,
    patient_id: int,
    options: dict,
    user_id: int | None = None,
    tenant_id: int | None = None,
) -> dict:
    """Generate patient card DOCX and store under storage/reports/{patient_id}/."""
    db = SessionLocal()
    try:
        buffer, cached_path = _load_cached_docx(patient_id, options, db)
        if buffer is not None and cached_path:
            return {
                "status": "completed",
                "patient_id": patient_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "file_path": cached_path,
                "task_id": self.request.id,
                "cached": True,
            }

        generator = DocxGenerator(db)
        buffer = generator.generate_patient_card(patient_id, options)
        file_path = save_docx_to_patient_reports(patient_id, buffer, suffix="patient_card")
        _store_docx_cache(patient_id, options, buffer, file_path, db)
        logger.info(
            "Async DOCX patient card ready for patient %s (user=%s, task=%s): %s",
            patient_id,
            user_id,
            self.request.id,
            file_path,
        )
        return {
            "status": "completed",
            "patient_id": patient_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "file_path": file_path,
            "task_id": self.request.id,
            "cached": False,
        }
    except Exception as exc:
        logger.exception("Async DOCX generation failed for patient %s: %s", patient_id, exc)
        return {"status": "failed", "error": str(exc), "patient_id": patient_id}
    finally:
        db.close()
