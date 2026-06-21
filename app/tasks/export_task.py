"""Asynchronous Excel export for large datasets (> EXPORT_MAX_ROWS)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.services.excel_export import ExcelExporter
from app.services.export_data import collect_export_rows
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_EXPORTER_METHODS = {
    "patients": "export_patients",
    "documents": "export_documents",
    "predictions": "export_predictions",
    "users": "export_users",
    "audit": "export_audit",
}


@celery_app.task(bind=True, name="app.tasks.export_task.generate_export")
def generate_export(self, entity: str, user_id: int, tenant_id: int | None, filters: dict, columns: list) -> dict:
    """Build an .xlsx file on disk and return its job id + relative path."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"status": "failed", "error": "User not found"}

        # Hard cap to avoid unbounded memory on pathological requests.
        hard_cap = max(settings.EXPORT_MAX_ROWS * 10, settings.EXPORT_MAX_ROWS)
        rows = collect_export_rows(db, entity, user, tenant_id, filters, hard_cap)

        exporter = ExcelExporter()
        method = getattr(exporter, _EXPORTER_METHODS[entity])
        buffer = method(rows, columns or None)

        export_dir = Path(settings.EXPORT_TEMP_DIR)
        export_dir.mkdir(parents=True, exist_ok=True)
        job_id = self.request.id
        filename = f"{entity}_export_{job_id}.xlsx"
        file_path = export_dir / filename
        file_path.write_bytes(buffer.getvalue())

        logger.info("Export %s ready: %s (%d rows)", entity, file_path, len(rows))
        return {"status": "completed", "job_id": job_id, "file": filename, "rows": len(rows)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Export task failed for %s: %s", entity, exc)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
