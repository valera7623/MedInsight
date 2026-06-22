#!/usr/bin/env python3
"""Tests for DICOM frame annotations (Phase 12c)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["DICOM_ENABLED"] = "true"
os.environ["DICOM_ANNOTATIONS_ENABLED"] = "true"
os.environ["ENCRYPTION_ENABLED"] = "false"
_dicom_dir = tempfile.mkdtemp(prefix="medinsight_ann_test_")
os.environ["DICOM_STORAGE_PATH"] = _dicom_dir

_seed_counter = 0


def _seed_frame():
    from datetime import date

    from app.auth import hash_password
    from app.database import Base, SessionLocal, bootstrap_system, engine
    from app.models import DicomFrame, DicomSeries, DicomStudy, Patient, Tenant, User

    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter

    Base.metadata.create_all(bind=engine)
    bootstrap_system()
    db = SessionLocal()
    tenant = db.query(Tenant).first()
    user = User(
        tenant_id=tenant.id,
        email=f"annotate{suffix}@example.com",
        password_hash=hash_password("secret"),
        full_name="Annotator",
        role="doctor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    patient = Patient(
        tenant_id=tenant.id,
        user_id=user.id,
        first_name="Ann",
        last_name="Patient",
        birth_date=date(1990, 5, 5),
        gender="F",
        phone="+70000000099",
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    study = DicomStudy(
        patient_id=patient.id,
        tenant_id=tenant.id,
        user_id=user.id,
        study_uid=f"1.2.3.annotate.study.{suffix}",
        status="ready",
        modality="CT",
    )
    db.add(study)
    db.commit()
    db.refresh(study)

    series = DicomSeries(
        study_id=study.id,
        series_uid=f"1.2.3.annotate.series.{suffix}",
        series_number=1,
        modality="CT",
    )
    db.add(series)
    db.commit()
    db.refresh(series)

    png_path = Path(_dicom_dir) / "frame.png"
    png_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    frame = DicomFrame(
        series_id=series.id,
        instance_uid=f"1.2.3.annotate.frame.{suffix}",
        frame_number=0,
        image_path=str(png_path),
        width=64,
        height=64,
        pixel_spacing={"row": 0.5, "col": 0.5},
    )
    db.add(frame)
    db.commit()
    db.refresh(frame)
    return db, user, frame


def test_annotation_service_crud() -> None:
    from app.services.dicom_annotations import DicomAnnotationService

    db, user, frame = _seed_frame()
    try:
        svc = DicomAnnotationService(db)

        ann = svc.create_annotation(
            {
                "frame_id": frame.id,
                "type": "rectangle",
                "coordinates": {"x1": 10, "y1": 10, "x2": 50, "y2": 40},
                "color": "#FF0000",
                "label": "Tumor",
            },
            user_id=user.id,
        )
        assert ann.id
        assert ann.type == "rectangle"
        assert ann.label == "Tumor"

        items = svc.get_annotations(frame.id)
        assert len(items) == 1

        by_uid = svc.get_annotations_for_frame(frame.instance_uid)
        assert len(by_uid) == 1

        updated = svc.update_annotation(
            ann.id,
            {"label": "Lesion", "coordinates": {"x1": 12, "y1": 12, "x2": 48, "y2": 38}},
            user_id=user.id,
        )
        assert updated.label == "Lesion"

        exported = svc.export_annotations_to_json(frame.id)
        payload = json.loads(exported)
        assert payload["frame_id"] == frame.id
        assert len(payload["annotations"]) == 1

        geo = json.loads(svc.export_annotations_to_geojson(frame.id))
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) == 1

        assert svc.delete_annotation(ann.id, user_id=user.id) is True
        assert svc.get_annotations(frame.id) == []
        print("PASS annotation service CRUD")
    finally:
        db.close()


def test_annotation_api() -> None:
    from fastapi.testclient import TestClient

    from app.auth import create_access_token
    from app.database import SessionLocal
    from app.main import app
    from app.models import DicomFrame, User
    from app.services.dicom_annotations import DicomAnnotationService

    db, user, frame = _seed_frame()
    try:
        token = create_access_token(user)
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}

        r = client.post(
            "/api/dicom/annotations",
            headers=headers,
            json={
                "frame_id": frame.id,
                "type": "rectangle",
                "coordinates": {"x1": 5, "y1": 5, "x2": 30, "y2": 25},
                "color": "#00FF00",
                "label": "ROI",
            },
        )
        assert r.status_code == 201, r.text
        ann_id = r.json()["id"]

        r2 = client.get(f"/api/dicom/annotations/frame/{frame.id}", headers=headers)
        assert r2.status_code == 200
        assert len(r2.json()) >= 1

        r3 = client.put(
            f"/api/dicom/annotations/{ann_id}",
            headers=headers,
            json={"label": "Updated ROI"},
        )
        assert r3.status_code == 200
        assert r3.json()["label"] == "Updated ROI"

        r4 = client.post(f"/api/dicom/annotations/export/{frame.id}", headers=headers)
        assert r4.status_code == 200
        assert "json" in r4.json()

        r5 = client.delete(f"/api/dicom/annotations/{ann_id}", headers=headers)
        assert r5.status_code == 204

        svc = DicomAnnotationService(db)
        svc.create_annotation(
            {
                "frame_id": frame.id,
                "type": "line",
                "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                "color": "#0000FF",
            },
            user_id=user.id,
        )
        frame2 = db.query(DicomFrame).filter(DicomFrame.id != frame.id).first()
        if not frame2:
            from app.models import DicomSeries

            series = db.query(DicomSeries).first()
            frame2 = DicomFrame(
                series_id=series.id,
                instance_uid=f"{frame.instance_uid}.copy",
                frame_number=1,
                image_path=frame.image_path,
                width=64,
                height=64,
            )
            db.add(frame2)
            db.commit()
            db.refresh(frame2)

        cloned = svc.clone_annotations_to_frame(frame.id, frame2.id, user_id=user.id)
        assert cloned >= 1
        print("PASS annotation API")
    finally:
        db.close()


def main() -> None:
    test_annotation_service_crud()
    test_annotation_api()
    print("\nAll annotation tests passed.")


if __name__ == "__main__":
    main()
