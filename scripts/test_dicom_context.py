#!/usr/bin/env python3
"""Test DICOM clinical context extraction and DICOM-enriched predictions."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["DICOM_ENABLED"] = "true"
os.environ["DICOM_RAG_ENABLED"] = "true"
os.environ["ENCRYPTION_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""


def _bootstrap_study() -> tuple[str, int]:
    from app.database import SessionLocal
    from app.models import DicomAnnotation, DicomFrame, DicomSeries, DicomStudy, Patient, Tenant, User
    from app.auth import hash_password

    db = SessionLocal()
    tenant = Tenant(name="Test", subdomain="test-dicom-ctx", is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="dicom_ctx@test.local",
        password_hash=hash_password("test"),
        full_name="DICOM Ctx Doctor",
        role="doctor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    patient = Patient(
        tenant_id=tenant.id,
        user_id=user.id,
        first_name="John",
        last_name="Doe",
        birth_date=datetime(1960, 1, 15).date(),
        gender="M",
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    study_uid = "1.2.3.4.5.6.7.8.9"
    study = DicomStudy(
        tenant_id=tenant.id,
        user_id=user.id,
        patient_id=patient.id,
        study_uid=study_uid,
        study_date=datetime(2026, 1, 15),
        study_description="CT Chest with contrast",
        modality="CT",
        body_part="CHEST",
        patient_name_dicom="Doe^John",
        status="ready",
        num_series=1,
        num_instances=1,
    )
    db.add(study)
    db.commit()
    db.refresh(study)

    series = DicomSeries(
        study_id=study.id,
        series_uid=f"{study_uid}.1",
        series_description="Chest axial",
        modality="CT",
        num_instances=1,
    )
    db.add(series)
    db.commit()
    db.refresh(series)

    frame = DicomFrame(
        series_id=series.id,
        instance_uid=f"{study_uid}.1.1",
        frame_number=0,
        image_path="/tmp/frame.png",
        width=512,
        height=512,
        pixel_spacing={"row": 0.5, "col": 0.5},
    )
    db.add(frame)
    db.commit()
    db.refresh(frame)

    ann = DicomAnnotation(
        frame_id=frame.id,
        user_id=user.id,
        type="rectangle",
        coordinates={"x": 100, "y": 120, "width": 84, "height": 70},
        label="right upper lobe mass",
        measurement_value=28.0,
        measurement_unit="mm",
    )
    db.add(ann)
    db.commit()

    db.close()
    return study_uid, patient.id


def test_context_extraction() -> None:
    from app.database import SessionLocal
    from app.services.dicom_rag import get_dicom_rag_service
    from app.services.dicom_text_extractor import DicomTextExtractor
    from app.services.predictor import predict_risk_with_dicom

    study_uid, patient_id = _bootstrap_study()
    db = SessionLocal()
    try:
        extractor = DicomTextExtractor(db)
        metadata = extractor.extract_metadata(study_uid)
        assert metadata["modality"] == "CT"
        assert metadata["body_part"] == "CHEST"

        measurements = extractor.extract_measurements(study_uid)
        assert len(measurements) >= 1

        study = extractor.process_study(study_uid)
        assert study.clinical_context
        assert study.radiology_findings is not None

        ctx = json.loads(study.clinical_context)
        assert ctx["study"]["modality"] == "CT"
        assert "findings" in ctx
        print("OK: metadata, measurements, clinical context")

        rag = get_dicom_rag_service()
        rag.index_dicom_study(
            study_uid,
            clinical_context=study.clinical_context,
            metadata={"modality": "CT", "body_part": "CHEST", "findings": study.radiology_findings},
        )
        similar = rag.search_similar_studies(study_uid, limit=3)
        assert isinstance(similar, list)
        print("OK: DICOM RAG index/search")

        user_id = study.user_id
        tenant_id = study.tenant_id
        prediction = predict_risk_with_dicom(db, patient_id, user_id, tenant_id=tenant_id)
        assert prediction.prediction
        assert prediction.prediction.get("source") in {"rule_based", "gpt", "gpt_dicom"}
        assert "dicom_sources" in (prediction.prediction or {})
        print("OK: predict_risk_with_dicom (rule-based fallback without API key)")
        print(json.dumps(prediction.prediction, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    test_context_extraction()
    print("All DICOM context tests passed.")
