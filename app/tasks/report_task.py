"""Celery task: generate PDF report from template."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import GeneratedReport, ReportTemplate
from app.services.templates.report_data import CONTEXT_BUILDERS
from app.services.templates.template_renderer import TemplateRenderer
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _generate_report_sync(report_id: int, options: dict | None = None) -> dict:
    options = options or {}
    db = SessionLocal()
    try:
        report = db.get(GeneratedReport, report_id)
        if not report:
            return {"status": "failed", "error": "Report not found"}

        template = db.get(ReportTemplate, report.template_id)
        if not template:
            report.status = "failed"
            report.error_message = "Template not found"
            db.commit()
            return {"status": "failed", "error": "Template not found"}

        report.status = "generating"
        db.commit()

        data = report.report_data or {}
        if not data.get("patient"):
            builder = CONTEXT_BUILDERS.get(template.template_type, CONTEXT_BUILDERS["clinical"])
            if template.template_type == "dicom":
                data = builder(db, report.patient_id, study_uid=options.get("study_uid"))
            else:
                data = builder(db, report.patient_id)
            report.report_data = data

        renderer = TemplateRenderer(db)
        pdf_bytes = renderer.render_to_pdf(
            template.id,
            data,
            watermark=options.get("watermark"),
        )

        out_dir = Path(settings.REPORTS_STORAGE_PATH) / str(report.patient_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"report_{report_id}.pdf"
        out_path.write_bytes(pdf_bytes)

        max_bytes = settings.REPORTS_MAX_FILE_SIZE_MB * 1024 * 1024
        if out_path.stat().st_size > max_bytes:
            out_path.unlink(missing_ok=True)
            raise RuntimeError("Generated PDF exceeds size limit")

        report.pdf_path = str(out_path)
        report.status = "completed"
        report.completed_at = datetime.utcnow()
        report.error_message = None
        db.commit()
        logger.info("Report %s generated: %s", report_id, out_path)
        return {"status": "completed", "report_id": report_id, "pdf_path": str(out_path)}
    except Exception as exc:
        logger.exception("Report generation failed for %s: %s", report_id, exc)
        try:
            report = db.get(GeneratedReport, report_id)
            if report:
                report.status = "failed"
                report.error_message = str(exc)[:1000]
                db.commit()
        except Exception:
            db.rollback()
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.report_task.generate_report_from_template")
def generate_report_from_template_task(self, report_id: int, options: dict | None = None) -> dict:
    return _generate_report_sync(report_id, options)


def generate_report_from_template(report_id: int, options: dict | None = None) -> dict | str:
    """Enqueue via Celery or run synchronously. Returns task id or result dict."""
    from app.tasks.celery_app import redis_available

    if redis_available():
        result = generate_report_from_template_task.delay(report_id, options)
        return result.id
    return _generate_report_sync(report_id, options)
