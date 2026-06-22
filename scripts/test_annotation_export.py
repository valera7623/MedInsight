#!/usr/bin/env python3
"""Tests for annotation export (JSON, GeoJSON, PDF) — Phase 12d."""

from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["DICOM_ANNOTATIONS_ENABLED"] = "true"
os.environ["ENCRYPTION_ENABLED"] = "false"
_dicom_dir = tempfile.mkdtemp(prefix="medinsight_export_test_")
os.environ["DICOM_STORAGE_PATH"] = _dicom_dir

_seed_counter = 0


def _seed():
    global _seed_counter
    from datetime import date

    from app.auth import hash_password
    from app.database import Base, SessionLocal, bootstrap_system, engine
    from app.models import DicomFrame, DicomSeries, DicomStudy, Patient, Tenant, User
    from app.services.dicom_annotations import DicomAnnotationService

    _seed_counter += 1
    suffix = _seed_counter

    Base.metadata.create_all(bind=engine)
    bootstrap_system()
    db = SessionLocal()
    tenant = db.query(Tenant).first()
    user = User(
        tenant_id=tenant.id,
        email=f"export{suffix}@example.com",
        password_hash=hash_password("secret"),
        full_name="Export Doctor",
        role="doctor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    patient = Patient(
        tenant_id=tenant.id,
        user_id=user.id,
        first_name="Exp",
        last_name="Patient",
        birth_date=date(1985, 3, 3),
        gender="M",
        phone="+70000000111",
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    study = DicomStudy(
        patient_id=patient.id,
        tenant_id=tenant.id,
        user_id=user.id,
        study_uid=f"1.2.3.export.study.{suffix}",
        status="ready",
        modality="CT",
        study_description="CT Chest",
    )
    db.add(study)
    db.commit()
    db.refresh(study)

    series = DicomSeries(
        study_id=study.id,
        series_uid=f"1.2.3.export.series.{suffix}",
        series_number=1,
        modality="CT",
        series_description="Axial",
    )
    db.add(series)
    db.commit()
    db.refresh(series)

    png_path = os.path.join(_dicom_dir, f"frame_{suffix}.png")
    try:
        from PIL import Image

        Image.new("RGB", (64, 64), color=(128, 128, 128)).save(png_path, format="PNG")
    except ImportError:
        with open(png_path, "wb") as f:
            f.write(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

    frame = DicomFrame(
        series_id=series.id,
        instance_uid=f"1.2.3.export.frame.{suffix}",
        frame_number=0,
        image_path=png_path,
        width=64,
        height=64,
    )
    db.add(frame)
    db.commit()
    db.refresh(frame)

    svc = DicomAnnotationService(db)
    svc.create_annotation(
        {
            "frame_id": frame.id,
            "type": "rectangle",
            "coordinates": {"x1": 10, "y1": 10, "x2": 50, "y2": 40},
            "color": "#FF0000",
            "label": "Tumor",
            "measurement_value": 12.5,
            "measurement_unit": "mm",
        },
        user_id=user.id,
    )
    return db, user, frame


def test_export_json_geojson_pdf() -> None:
    from app.services.annotation_export import AnnotationExportService

    db, user, frame = _seed()
    try:
        svc = AnnotationExportService(db)

        json_str = svc.export_to_json(frame.id, user=user)
        payload = json.loads(json_str)
        assert payload["version"] == "1.0"
        assert payload["frame"]["instance_uid"] == frame.instance_uid
        assert len(payload["annotations"]) == 1
        assert payload["annotations"][0]["label"] == "Tumor"
        print("PASS export JSON")

        geo_str = svc.export_to_geojson(frame.id)
        geo = json.loads(geo_str)
        assert geo["type"] == "FeatureCollection"
        assert geo["features"][0]["geometry"]["type"] == "Polygon"
        print("PASS export GeoJSON")

        pdf_bytes = svc.export_to_pdf(frame.id, user=user)
        assert pdf_bytes[:4] == b"%PDF"
        assert len(pdf_bytes) > 500
        print("PASS export PDF")
    finally:
        db.close()


def test_export_api() -> None:
    from fastapi.testclient import TestClient

    from app.auth import create_access_token
    from app.main import app

    db, user, frame = _seed()
    try:
        token = create_access_token(user)
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/api/dicom/annotations/export/json/{frame.id}", headers=headers)
        assert r.status_code == 200
        data = json.loads(r.text)
        assert data["metadata"]["total_annotations"] == 1

        r2 = client.get(f"/api/dicom/annotations/export/geojson/{frame.id}", headers=headers)
        assert r2.status_code == 200

        r3 = client.get(f"/api/dicom/annotations/export/pdf/{frame.id}", headers=headers)
        assert r3.status_code == 200
        assert r3.content[:4] == b"%PDF"

        r4 = client.put(
            f"/api/dicom/annotations/{data['annotations'][0]['id']}/label",
            headers=headers,
            json={"label": "Updated"},
        )
        assert r4.status_code == 200
        assert r4.json()["label"] == "Updated"
        print("PASS export + edit API")
    finally:
        db.close()


def main() -> None:
    test_export_json_geojson_pdf()
    test_export_api()
    print("\nAll annotation export tests passed.")


if __name__ == "__main__":
    main()
