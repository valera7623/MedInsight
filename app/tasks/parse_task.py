import logging
from datetime import datetime

from app.database import SessionLocal
from app.models import AnalysisJob, Document
from app.services.encryption import decrypt_file
from app.services.extractor import extract_entities
from app.services.parser import parse_document, parse_document_from_bytes
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _parse_doc(doc: Document) -> str:
    if doc.is_encrypted or doc.file_path.endswith(".age"):
        content = decrypt_file(doc.file_path)
        return parse_document_from_bytes(content, doc.filename)
    return parse_document(doc.file_path)


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

        text = _parse_doc(doc)
        parsed = extract_entities(text)
        doc.parsed_data = parsed
        doc.status = "parsed"
        doc.parsed_at = datetime.utcnow()

        job.status = "completed"
        job.result = {"document_id": document_id, "parsed_data": parsed}
        job.completed_at = datetime.utcnow()
        db.commit()

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
