"""DSAR (data subject access request) export and erasure."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Document, Patient, Prediction, User
from app.services.patient_deletion import delete_patient_with_dependencies
from app.services.phi_crypto import decrypt_field

logger = logging.getLogger(__name__)


def build_patient_dsar_bundle(db: Session, patient_id: int, tenant_id: int) -> dict[str, Any]:
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id, Patient.tenant_id == tenant_id)
        .first()
    )
    if not patient:
        raise ValueError("Patient not found")

    docs = db.query(Document).filter(Document.patient_id == patient.id).all()
    preds = db.query(Prediction).filter(Prediction.patient_id == patient.id).all()

    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "patient": {
            "id": patient.id,
            "public_id": str(patient.public_id),
            "first_name": decrypt_field(patient.first_name),
            "last_name": decrypt_field(patient.last_name),
            "middle_name": decrypt_field(getattr(patient, "middle_name", None)),
            "birth_date": str(patient.birth_date) if patient.birth_date else None,
            "gender": patient.gender,
            "phone": decrypt_field(patient.phone),
            "email": decrypt_field(getattr(patient, "email", None)),
            "created_at": patient.created_at.isoformat() if patient.created_at else None,
        },
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
        "predictions": [
            {
                "id": p.id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "prediction": p.prediction,
            }
            for p in preds
        ],
    }


def export_patient_dsar_json(db: Session, patient_id: int, tenant_id: int) -> str:
    return json.dumps(build_patient_dsar_bundle(db, patient_id, tenant_id), ensure_ascii=False, indent=2)


def erase_patient_dsar(db: Session, patient_id: int, tenant_id: int, *, actor: User) -> None:
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id, Patient.tenant_id == tenant_id)
        .first()
    )
    if not patient:
        raise ValueError("Patient not found")
    delete_patient_with_dependencies(db, patient)
