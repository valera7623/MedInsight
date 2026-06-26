"""Asynchronous DOCX generation for patient cards."""

from __future__ import annotations

import logging

from app.database import SessionLocal
from app.services.docx_generator import DocxGenerator, save_docx_to_patient_reports
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
    """Generate patient card DOCX and store under storage/reports/{patient_id}/."""
    db = SessionLocal()
    try:
        generator = DocxGenerator(db)
        buffer = generator.generate_patient_card(patient_id, options)
        file_path = save_docx_to_patient_reports(patient_id, buffer, suffix="patient_card")
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
        }
    except Exception as exc:
        logger.exception("Async DOCX generation failed for patient %s: %s", patient_id, exc)
        return {"status": "failed", "error": str(exc), "patient_id": patient_id}
    finally:
        db.close()
