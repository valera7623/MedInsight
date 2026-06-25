import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import AnalysisJob, Appointment, Document

logger = logging.getLogger(__name__)


def delete_document_with_dependencies(db: Session, doc: Document) -> None:
    """Remove document file, related jobs and DB record."""
    db.query(Appointment).filter(Appointment.patient_document_id == doc.id).update(
        {Appointment.patient_document_id: None},
        synchronize_session=False,
    )
    db.query(AnalysisJob).filter(AnalysisJob.document_id == doc.id).delete(synchronize_session=False)

    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to delete document file %s: %s", doc.file_path, exc)

    db.delete(doc)
    db.commit()
