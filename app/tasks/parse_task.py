import asyncio
import logging
from datetime import datetime

from app.config import settings
from app.database import SessionLocal
from app.models import AnalysisJob, Document, Patient
from app.services.ai_parser import AIParser
from app.services.ai_parser_validator import AIParserValidator
from app.services.encryption import decrypt_file
from app.services.extractor import extract_entities
from app.services.parser import parse_document, parse_document_from_bytes
from app.services.self_healing import with_self_healing
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_ai_parser = AIParser()
_ai_validator = AIParserValidator()


def _telegram_analysis_completed(db, job: AnalysisJob, doc: Document, parsed: dict) -> None:
    if not settings.TELEGRAM_BOT_ENABLED:
        return
    try:
        patient = db.query(Patient).filter(Patient.id == job.patient_id).first()
        patient_name = f"{patient.last_name} {patient.first_name}".strip() if patient else "пациент"
        diagnoses = parsed.get("diagnoses") or []
        summary = ", ".join(str(d) for d in diagnoses[:3]) if diagnoses else "данные извлечены"
        if len(diagnoses) > 3:
            summary += "…"

        from app.bot.services.notification_service import get_notification_service

        get_notification_service().send_analysis_completed_sync(
            user_id=job.user_id,
            patient_name=patient_name,
            analysis_id=job.id,
            result_summary=summary,
            patient_id=job.patient_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram analysis notification failed for job %s: %s", job.id, exc)


def _extract_raw_text(doc: Document) -> str:
    if doc.is_encrypted or doc.file_path.endswith(".age"):
        content = decrypt_file(doc.file_path)
        return parse_document_from_bytes(content, doc.filename)
    return parse_document(doc.file_path)


@with_self_healing("parser")
def _parse_doc(doc: Document, *, document_id: int | None = None, tenant_id: int | None = None) -> str:
    return _extract_raw_text(doc)


@with_self_healing("extractor")
def _extract(text: str, *, document_id: int | None = None, tenant_id: int | None = None) -> dict:
    return extract_entities(text)


@celery_app.task(bind=True, name="app.tasks.parse_task.parse_document_task")
def parse_document_task(self, job_id: int, document_id: int) -> dict:
    db = SessionLocal()
    doc = None
    job = None
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        doc = db.query(Document).filter(Document.id == document_id).first()

        if not job or not doc:
            logger.error("Job %s or document %s not found", job_id, document_id)
            return {"status": "failed", "error": "Job or document not found"}

        job.status = "processing"
        job.celery_task_id = self.request.id
        doc.status = "processing"
        db.commit()

        text = _parse_doc(doc, document_id=document_id, tenant_id=doc.tenant_id)
        parsed = _extract(text, document_id=document_id, tenant_id=doc.tenant_id)
        doc.parsed_data = parsed
        doc.status = "parsed"
        doc.parsed_at = datetime.utcnow()

        job.status = "completed"
        job.result = {"document_id": document_id, "parsed_data": parsed}
        job.completed_at = datetime.utcnow()
        db.commit()

        try:
            from app.tasks.webhook_task import fire_event

            fire_event(
                "analysis.completed",
                job.tenant_id,
                patient_id=job.patient_id,
                analysis_id=job.id,
                document_id=document_id,
                result={"diagnoses": parsed.get("diagnoses", []), "medications": parsed.get("medications", [])},
            )
        except Exception as hook_exc:  # webhook failure must not fail the job
            logger.warning("Webhook dispatch failed for job %s: %s", job_id, hook_exc)

        try:
            from app.websocket.events import EVENT_DOCUMENT_PARSED, publish_event

            publish_event(
                EVENT_DOCUMENT_PARSED,
                {
                    "document_id": document_id,
                    "patient_id": job.patient_id,
                    "status": "parsed",
                    "diagnoses": parsed.get("diagnoses", []),
                    "medications": parsed.get("medications", []),
                },
                user_id=job.user_id,
                tenant_id=job.tenant_id,
            )
        except Exception as ws_exc:  # noqa: BLE001
            logger.debug("WS document.parsed event failed for job %s: %s", job_id, ws_exc)

        _telegram_analysis_completed(db, job, doc, parsed)

        logger.info("Document %s parsed successfully (job %s)", document_id, job_id)
        return {"status": "completed", "document_id": document_id}

    except Exception as exc:
        logger.exception("Parse task failed for document %s: %s", document_id, exc)
        if doc := db.query(Document).filter(Document.id == document_id).first():
            doc.status = "failed"
            doc.parsed_data = {"error": str(exc), "full_text": ""}
        if job := db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first():
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
        db.commit()
        return {"status": "failed", "error": str(exc)}

    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.parse_task.parse_document_with_ai", max_retries=3)
def parse_document_with_ai(self, document_id: int) -> dict:
    """Hybrid parse: classic text extraction + GPT structuring."""
    db = SessionLocal()
    doc = None
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error("Document %s not found for AI parse", document_id)
            return {"status": "error", "message": "Document not found"}

        if not settings.AI_PARSER_ENABLED:
            return {"status": "skipped", "message": "AI parser disabled"}

        doc.status = "processing"
        db.commit()

        text = _extract_raw_text(doc)
        ai_result = asyncio.run(_ai_parser.parse_text(text, doc.document_type or "discharge"))

        if not _ai_validator.validate(ai_result):
            _ai_validator.log_validation_errors(document_id, ai_result)
            doc.status = "failed"
            doc.parsed_data = {
                "error": "AI parsing validation failed",
                "full_text": text,
                "parser": "ai",
            }
            db.commit()
            return {"status": "error", "message": "AI parsing validation failed"}

        confidence = float(ai_result.pop("_confidence", 0.0))
        model = ai_result.pop("_model", None)
        stored = _ai_validator.normalize_for_storage(ai_result)
        if model:
            stored["ai_model"] = model
        stored["full_text"] = text

        doc.parsed_data = stored
        doc.parsed_by_ai = True
        doc.parsed_at = datetime.utcnow()
        doc.parse_confidence = confidence
        doc.status = "parsed"
        db.commit()

        try:
            from app.websocket.events import EVENT_DOCUMENT_PARSED, publish_event

            publish_event(
                EVENT_DOCUMENT_PARSED,
                {
                    "document_id": document_id,
                    "patient_id": doc.patient_id,
                    "status": "parsed",
                    "parsed_by_ai": True,
                    "diagnoses": stored.get("diagnoses", []),
                    "medications": stored.get("medications", []),
                },
                user_id=doc.user_id,
                tenant_id=doc.tenant_id,
            )
        except Exception as ws_exc:  # noqa: BLE001
            logger.debug("WS document.parsed (AI) failed for %s: %s", document_id, ws_exc)

        logger.info("Document %s parsed with AI (confidence=%.2f)", document_id, confidence)
        return {"status": "success", "document_id": document_id, "parse_confidence": confidence}

    except Exception as exc:
        logger.exception("AI parse task failed for document %s: %s", document_id, exc)
        if doc := db.query(Document).filter(Document.id == document_id).first():
            doc.status = "failed"
            doc.parsed_data = {"error": str(exc), "full_text": "", "parser": "ai"}
            db.commit()
        return {"status": "error", "message": str(exc)}

    finally:
        db.close()
