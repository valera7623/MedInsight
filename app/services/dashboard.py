from collections import Counter

from sqlalchemy.orm import Session

from app.models import Document, Patient


def get_dashboard_data(db: Session, user_id: int) -> dict:
    patients = db.query(Patient).filter(Patient.user_id == user_id).all()

    documents = (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .all()
    )

    diagnoses_counter: Counter = Counter()
    medications_counter: Counter = Counter()

    for doc in documents:
        if not doc.parsed_data:
            continue
        for diagnosis in doc.parsed_data.get("diagnoses", []):
            diagnoses_counter[diagnosis] += 1
        for medication in doc.parsed_data.get("medications", []):
            medications_counter[medication] += 1

    recent_patients = sorted(patients, key=lambda p: p.created_at, reverse=True)[:5]

    return {
        "total_patients": len(patients),
        "total_documents": len(documents),
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
