from collections import Counter

from sqlalchemy.orm import Session

from app.models import Document, Patient, User, DicomStudy
from app.services.access import patients_query
from app.services.extractor import diagnoses_from_parsed_data, medications_from_parsed_data


def get_dashboard_data(
    db: Session, user: User, tenant_id: int | None = None, department_id: int | None = None
) -> dict:
    patients_q = patients_query(db, user, tenant_id)
    if department_id is not None:
        patients_q = patients_q.filter(Patient.department_id == department_id)

    patients = patients_q.all()
    patient_ids = [p.id for p in patients]

    if patient_ids:
        documents = db.query(Document).filter(Document.patient_id.in_(patient_ids)).all()
        dicom_studies = (
            db.query(DicomStudy)
            .filter(DicomStudy.patient_id.in_(patient_ids), DicomStudy.status == "ready")
            .all()
        )
    else:
        documents = []
        dicom_studies = []

    modality_counter: Counter = Counter()
    body_part_counter: Counter = Counter()
    for ds in dicom_studies:
        if ds.modality:
            modality_counter[ds.modality] += 1
        if ds.body_part:
            body_part_counter[ds.body_part] += 1

    diagnoses_counter: Counter = Counter()
    medications_counter: Counter = Counter()

    for doc in documents:
        if not doc.parsed_data:
            continue
        for diagnosis in diagnoses_from_parsed_data(doc.parsed_data):
            diagnoses_counter[diagnosis] += 1
        for medication in medications_from_parsed_data(doc.parsed_data):
            medications_counter[medication] += 1

    recent_patients = sorted(patients, key=lambda p: p.created_at, reverse=True)[:5]

    return {
        "total_patients": len(patients),
        "total_documents": len(documents),
        "total_dicom_studies": len(dicom_studies),
        "dicom_modalities": dict(modality_counter.most_common(10)),
        "dicom_body_parts": dict(body_part_counter.most_common(10)),
        "diagnoses": dict(diagnoses_counter.most_common(20)),
        "medications": dict(medications_counter.most_common(20)),
        "recent_patients": [
            {
                "id": p.id,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "middle_name": p.middle_name,
                "birth_date": p.birth_date.isoformat(),
                "gender": p.gender,
                "created_at": p.created_at.isoformat(),
            }
            for p in recent_patients
        ],
    }
