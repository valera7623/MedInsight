"""Asynchronous DOCX generation for patient cards with Redis + static cache."""

from __future__ import annotations

import logging

from app.database import SessionLocal
from app.services.cache_manager import get_cache_manager
from app.services.docx_generator import DocxGenerator
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.docx_task.generate_patient_card_async")
def generate_patient_card_async(
    self,
    patient_id: int,
    options: dict,
    user_id: int | None = None,
    tenant_id: int | None = None,
) -> dict:
    """Generate patient card DOCX; cache in Redis (1h) and static disk."""
    db = SessionLocal()
    try:
        mgr = get_cache_manager(db)
        cached_bytes, cache_source = mgr.get_docx_sync(patient_id, options)
        if cached_bytes is not None:
            from app.services.static_cache import StaticCache

            static = StaticCache()
            static_path = static.get_file_path(static.get_cache_key(patient_id, options))
            file_path = str(static_path) if static_path.is_file() else mgr.set_docx_sync(
                patient_id, options, cached_bytes, also_save_report=True
            )
            return {
                "status": "completed",
                "patient_id": patient_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "options": options,
                "file_path": file_path,
                "task_id": self.request.id,
                "cached": True,
                "cache_source": cache_source,
            }

        generator = DocxGenerator(db)
        buffer = generator.generate_patient_card(patient_id, options)
        data = buffer.getvalue()
        file_path = mgr.set_docx_sync(patient_id, options, data, also_save_report=True)
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
            "options": options,
            "file_path": file_path,
            "task_id": self.request.id,
            "cached": False,
            "cache_source": "generated",
        }
    except Exception as exc:
        logger.exception("Async DOCX generation failed for patient %s: %s", patient_id, exc)
        return {"status": "failed", "error": str(exc), "patient_id": patient_id}
    finally:
        db.close()
