#!/usr/bin/env python3
"""Tests for DICOM parsing, PNG conversion and DB persistence."""

from __future__ import annotations

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
os.environ["ENCRYPTION_ENABLED"] = "false"
_dicom_dir = tempfile.mkdtemp(prefix="medinsight_dicom_test_")
os.environ["DICOM_STORAGE_PATH"] = _dicom_dir


def _make_sample_dicom(path: Path) -> None:
    import numpy as np
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.PatientName = "Test^Patient"
    ds.PatientID = "TEST001"
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = "CT"
    ds.BodyPartExamined = "HEAD"
    ds.StudyDate = "20240615"
    ds.StudyDescription = "Test CT Head"
    ds.SeriesNumber = 1
    ds.SeriesDescription = "Axial"
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 32
    ds.Columns = 32
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.WindowCenter = 2048
    ds.WindowWidth = 4096

    pixels = np.linspace(0, 4095, 32 * 32, dtype=np.uint16).reshape(32, 32)
    ds.PixelData = pixels.tobytes()
    ds.save_as(str(path))


def test_parser_validate_and_metadata() -> None:
    from app.services.dicom_parser import DicomParser

    sample = Path(tempfile.mkdtemp()) / "sample.dcm"
    _make_sample_dicom(sample)

    parser = DicomParser()
    assert parser.validate_dicom(str(sample)) is True

    parsed = parser.parse_dicom_file(str(sample))
    assert parsed["modality"] == "CT"
    assert parsed["body_part"] == "HEAD"
    assert parsed["patient_name"] == "Test^Patient"
    assert parsed["num_instances"] >= 1
    assert parsed["frames"][0]["png_bytes"][:8] == b"\x89PNG\r\n\x1a\n"
    print("PASS parser validate + metadata + PNG")


def test_storage_frames() -> None:
    from app.services.dicom_parser import DicomParser
    from app.services.dicom_storage import DicomStorage

    sample = Path(tempfile.mkdtemp()) / "sample.dcm"
    _make_sample_dicom(sample)
    parsed = DicomParser().parse_dicom_file(str(sample))
    storage = DicomStorage()

    frames = [(f["instance_uid"], f["frame_number"], f["png_bytes"]) for f in parsed["frames"]]
    paths = storage.store_frames(
        patient_id=1,
        study_uid=parsed["study_uid"],
        frames=frames,
    )
    assert len(paths) == len(frames)
    assert Path(paths[0]).exists()
    print("PASS storage frames")


def test_process_dicom_study_db() -> None:
    from datetime import date

    from app.auth import hash_password
    from app.database import Base, SessionLocal, bootstrap_system, engine
    from app.models import Department, DicomStudy, Patient, Tenant, User
    from app.tasks.dicom_task import process_dicom_study

    Base.metadata.create_all(bind=engine)
    bootstrap_system()
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).first()
        if not tenant:
            tenant = Tenant(name="Dicom Clinic", subdomain="dicom-test", settings={}, is_active=True)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        dept = Department(tenant_id=tenant.id, name="Radiology")
        db.add(dept)
        db.commit()
        db.refresh(dept)

        user = User(
            tenant_id=tenant.id,
            email="dicom@example.com",
            password_hash=hash_password("secret"),
            full_name="Dicom Doctor",
            role="doctor",
            department_id=dept.id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        patient = Patient(
            tenant_id=tenant.id,
            user_id=user.id,
            department_id=dept.id,
            first_name="Ivan",
            last_name="Ivanov",
            birth_date=date(1980, 1, 1),
            gender="M",
            phone="+70000000001",
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)

        sample = Path(tempfile.mkdtemp()) / "upload.dcm"
        _make_sample_dicom(sample)

        study = DicomStudy(
            patient_id=patient.id,
            tenant_id=tenant.id,
            user_id=user.id,
            study_uid="pending-test",
            status="processing",
            original_filename="upload.dcm",
        )
        db.add(study)
        db.commit()
        db.refresh(study)

        result = process_dicom_study(study.id, str(sample))
        assert result["status"] == "ready", result

        db.expire_all()
        study = db.query(DicomStudy).filter(DicomStudy.id == study.id).first()
        assert study.status == "ready"
        assert study.modality == "CT"
        assert study.num_instances >= 1
        assert study.series and study.series[0].frames
        print("PASS process_dicom_study DB")
    finally:
        db.close()


def test_dicom_api_list() -> None:
    from fastapi.testclient import TestClient

    from app.auth import create_access_token, hash_password
    from app.database import SessionLocal
    from app.main import app
    from app.models import User

    db = SessionLocal()
    user = db.query(User).filter(User.email == "dicom@example.com").first()
    if not user:
        print("SKIP dicom API (no user from prior test)")
        db.close()
        return
    token = create_access_token(user)
    db.close()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/dicom/studies", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    print("PASS dicom API list")


def test_dicom_api_delete() -> None:
    from fastapi.testclient import TestClient

    from app.auth import create_access_token
    from app.database import SessionLocal
    from app.main import app
    from app.models import DicomStudy, User

    db = SessionLocal()
    user = db.query(User).filter(User.email == "dicom@example.com").first()
    study = db.query(DicomStudy).filter(DicomStudy.status == "ready").first()
    if not user or not study:
        print("SKIP dicom API delete (no ready study)")
        db.close()
        return
    study_uid = study.study_uid
    token = create_access_token(user)
    db.close()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.delete(f"/api/dicom/studies/{study_uid}", headers=headers)
    assert r.status_code == 204, r.text

    db = SessionLocal()
    assert db.query(DicomStudy).filter(DicomStudy.study_uid == study_uid).first() is None
    db.close()
    print("PASS dicom API delete")


def test_dicom_duplicate_study_uid() -> None:
    from datetime import date

    from app.auth import hash_password
    from app.database import Base, SessionLocal, bootstrap_system, engine
    from app.models import Department, DicomStudy, Patient, Tenant, User
    from app.services.dicom_parser import DicomParser
    from app.services.dicom_persistence import ensure_unique_dicom_ids
    from app.services.dicom_parser import DicomParseError

    Base.metadata.create_all(bind=engine)
    bootstrap_system()
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).first()
        user = db.query(User).filter(User.email == "dicom@example.com").first()
        patient = db.query(Patient).first()
        if not user or not patient:
            dept = Department(tenant_id=tenant.id, name="Dup Rad")
            db.add(dept)
            db.commit()
            user = User(
                tenant_id=tenant.id,
                email="dup@example.com",
                password_hash=hash_password("secret"),
                full_name="Dup Doc",
                role="doctor",
                department_id=dept.id,
            )
            db.add(user)
            patient = Patient(
                tenant_id=tenant.id,
                user_id=user.id,
                department_id=dept.id,
                first_name="P",
                last_name="Dup",
                birth_date=date(1985, 1, 1),
                gender="M",
                phone="+7111",
            )
            db.add(patient)
            db.commit()
            db.refresh(user)
            db.refresh(patient)

        sample = Path(tempfile.mkdtemp()) / "dup.dcm"
        _make_sample_dicom(sample)
        parsed = DicomParser().parse_dicom_file(str(sample))

        existing = DicomStudy(
            patient_id=patient.id,
            tenant_id=tenant.id,
            user_id=user.id,
            study_uid=parsed["study_uid"],
            status="ready",
            num_series=1,
            num_instances=1,
        )
        db.add(existing)
        db.commit()

        pending = DicomStudy(
            patient_id=patient.id,
            tenant_id=tenant.id,
            user_id=user.id,
            study_uid="pending-dup-test",
            status="processing",
            num_series=0,
            num_instances=0,
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)

        try:
            ensure_unique_dicom_ids(db, pending, parsed)
            raise AssertionError("expected DicomParseError for duplicate study_uid")
        except DicomParseError:
            pass
        print("PASS duplicate study_uid detection")
    finally:
        db.close()


def main() -> None:
    test_parser_validate_and_metadata()
    test_storage_frames()
    test_process_dicom_study_db()
    test_dicom_api_list()
    test_dicom_api_delete()
    test_dicom_duplicate_study_uid()
    print("\nAll DICOM tests passed.")


if __name__ == "__main__":
    main()
