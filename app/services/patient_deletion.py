import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Appointment, DicomStudy, GeneratedReport, Patient
from app.services.dicom_persistence import delete_study_data
from app.services.dicom_storage import DicomStorage

logger = logging.getLogger(__name__)


def delete_patient_with_dependencies(db: Session, patient: Patient) -> None:
    """Remove patient and all dependent records (appointments, DICOM, reports, documents)."""
    patient_id = patient.id
    storage = DicomStorage()

    for appointment in db.query(Appointment).filter(Appointment.patient_id == patient_id).all():
        db.delete(appointment)
    db.flush()

    for study in db.query(DicomStudy).filter(DicomStudy.patient_id == patient_id).all():
        delete_study_data(db, study, storage)

    for report in db.query(GeneratedReport).filter(GeneratedReport.patient_id == patient_id).all():
        if report.pdf_path:
            try:
                Path(report.pdf_path).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to delete report PDF %s: %s", report.pdf_path, exc)
        db.delete(report)

    for doc in list(patient.documents):
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except OSError:
            pass

    db.delete(patient)
    db.commit()
