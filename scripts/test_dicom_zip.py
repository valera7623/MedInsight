#!/usr/bin/env python3
"""Tests for DICOM ZIP upload, extraction and processing."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import zipfile
from datetime import date
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
_zip_temp = tempfile.mkdtemp(prefix="medinsight_dicom_zip_")
os.environ["DICOM_STORAGE_PATH"] = _dicom_dir
os.environ["DICOM_ZIP_TEMP_DIR"] = _zip_temp
os.environ["DICOM_ZIP_MAX_FILES"] = "100"


def _make_sample_dicom(path: Path, *, study_uid: str | None = None, series_uid: str | None = None, instance_suffix: str = "") -> None:
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
    ds.PatientName = "Zip^Test"
    ds.PatientID = "ZIP001"
    ds.StudyInstanceUID = study_uid or generate_uid()
    ds.SeriesInstanceUID = series_uid or generate_uid()
    ds.Modality = "CT"
    ds.BodyPartExamined = "CHEST"
    ds.StudyDate = "20240615"
    ds.StudyDescription = f"ZIP Test {instance_suffix}"
    ds.SeriesNumber = 1
    ds.SeriesDescription = "Axial"
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 16
    ds.Columns = 16
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.WindowCenter = 2048
    ds.WindowWidth = 4096

    pixels = np.linspace(0, 4095, 16 * 16, dtype=np.uint16).reshape(16, 16)
    ds.PixelData = pixels.tobytes()
    ds.save_as(str(path))


def _make_zip_with_dicoms(count: int = 10) -> Path:
    import pydicom
    from pydicom.uid import generate_uid

    study_uid = generate_uid()
    series_uid = generate_uid()
    tmp = Path(tempfile.mkdtemp())
    zip_path = tmp / "study.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(count):
            dcm = tmp / f"slice_{i:03d}.dcm"
            _make_sample_dicom(dcm, study_uid=study_uid, series_uid=series_uid, instance_suffix=str(i))
            zf.write(dcm, arcname=f"series/slice_{i:03d}.dcm")

    return zip_path


def _make_zip_with_extensionless_dicoms(count: int = 3) -> Path:
    import pydicom
    from pydicom.uid import generate_uid

    study_uid = generate_uid()
    series_uid = generate_uid()
    tmp = Path(tempfile.mkdtemp())
    zip_path = tmp / "siemens_like.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(count):
            dcm = tmp / f"IM-{i:04d}"
            _make_sample_dicom(dcm, study_uid=study_uid, series_uid=series_uid, instance_suffix=str(i))
            zf.write(dcm, arcname=f"PA000001/ST000001/SE000001/IM-{i:04d}")

    return zip_path


def test_zip_extensionless_dicom_paths() -> None:
    from app.services.dicom_zip_processor import DicomZipProcessor

    zip_path = _make_zip_with_extensionless_dicoms(4)
    processor = DicomZipProcessor()

    assert processor.validate_archive(str(zip_path)) is True
    entries = processor.iter_archive_dicom_paths(str(zip_path))
    assert len(entries) == 4

    temp_dir = processor.extract_archive(str(zip_path))
    files = processor.scan_files(temp_dir)
    assert len(files) == 4
    processor.cleanup_temp(temp_dir)
    print("OK test_zip_extensionless_dicom_paths")


def test_zip_processor_validate_and_group() -> None:
    from app.services.dicom_zip_processor import DicomZipProcessor

    zip_path = _make_zip_with_dicoms(5)
    processor = DicomZipProcessor()

    assert processor.validate_zip(str(zip_path)) is True
    entries = processor.iter_zip_dicom_paths(str(zip_path))
    assert len(entries) == 5

    temp_dir = processor.extract_zip(str(zip_path))
    files = processor.scan_files(temp_dir)
    assert len(files) == 5

    groups = processor.group_by_study(files)
    assert len(groups) == 1

    structure = processor.process_study(files, patient_id=1)
    assert structure["num_series"] >= 1
    assert structure["num_instances"] >= 5

    processor.cleanup_temp(temp_dir)
    print("OK test_zip_processor_validate_and_group")


def test_zip_celery_task_db() -> None:
    from app.database import Base, bootstrap_system, engine, run_migrations, SessionLocal
    from app.models import DicomStudy, Department, Patient, Tenant, User
    from app.tasks.dicom_zip_task import process_dicom_zip

    Base.metadata.create_all(bind=engine)
    run_migrations()
    bootstrap_system()

    zip_path = _make_zip_with_dicoms(10)

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).first()
        if not tenant:
            tenant = Tenant(name="Zip Clinic", subdomain="zipclinic")
            db.add(tenant)
            db.flush()

        dept = Department(tenant_id=tenant.id, name="Radiology")
        db.add(dept)
        db.flush()

        user = User(
            tenant_id=tenant.id,
            department_id=dept.id,
            email="zipdoc@test.local",
            password_hash="x",
            full_name="Zip Doctor",
            role="doctor",
        )
        db.add(user)
        db.flush()

        patient = Patient(
            tenant_id=tenant.id,
            user_id=user.id,
            department_id=dept.id,
            first_name="Zip",
            last_name="Patient",
            birth_date=date(1990, 1, 1),
            gender="M",
            phone="+10000000000",
        )
        db.add(patient)
        db.commit()

        study = DicomStudy(
            patient_id=patient.id,
            tenant_id=tenant.id,
            user_id=user.id,
            study_uid="pending-zip-test",
            original_filename="study.zip",
            status="processing",
            total_files=10,
            zip_size_mb=0.1,
        )
        db.add(study)
        db.commit()
        study_id = study.id
        user_id = user.id
    finally:
        db.close()

    result = process_dicom_zip(study_id, str(zip_path), user_id)
    assert result["status"] == "ready", result
    assert result["num_instances"] >= 10

    db = SessionLocal()
    try:
        study = db.query(DicomStudy).filter(DicomStudy.id == study_id).first()
        assert study is not None
        assert study.status == "ready"
        assert study.total_files == 10
        assert study.processed_files == 10
        assert not study.study_uid.startswith("pending")
        assert len(study.series) >= 1
        frame_count = sum(len(s.frames) for s in study.series)
        assert frame_count >= 10
    finally:
        db.close()

    print("OK test_zip_celery_task_db")


def test_zip_api_route_validation() -> None:
    from fastapi.testclient import TestClient
    from app.database import Base, bootstrap_system, engine, run_migrations, SessionLocal
    from app.main import app
    from app.models import Department, Patient, Tenant, User
    from app.auth import create_access_token

    Base.metadata.create_all(bind=engine)
    run_migrations()
    bootstrap_system()

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.subdomain == "default").first()
        if not tenant:
            tenant = Tenant(name="Default", subdomain="default")
            db.add(tenant)
            db.flush()
        dept = Department(tenant_id=tenant.id, name="Dept")
        db.add(dept)
        db.flush()
        user = User(
            tenant_id=tenant.id,
            department_id=dept.id,
            email="apidoc@test.local",
            password_hash="x",
            full_name="API Doc",
            role="doctor",
        )
        db.add(user)
        db.flush()
        patient = Patient(
            tenant_id=tenant.id,
            user_id=user.id,
            department_id=dept.id,
            first_name="A",
            last_name="B",
            birth_date=date(1985, 1, 1),
            gender="F",
            phone="+1",
        )
        db.add(patient)
        db.commit()
        token = create_access_token(user)
        patient_id = patient.id
    finally:
        db.close()

    zip_path = _make_zip_with_dicoms(3)
    client = TestClient(app)

    with zip_path.open("rb") as f:
        res = client.post(
            "/api/dicom/upload-zip",
            headers={"Authorization": f"Bearer {token}"},
            data={"patient_id": str(patient_id)},
            files={"zip_file": ("study.zip", f, "application/zip")},
        )

    assert res.status_code == 202, res.text
    body = res.json()
    assert body["total_files"] == 3
    assert body["status"] in ("processing", "ready")
    print("OK test_zip_api_route_validation")


def main() -> None:
    test_zip_extensionless_dicom_paths()
    test_zip_processor_validate_and_group()
    test_zip_celery_task_db()
    test_zip_api_route_validation()
    print("\nAll DICOM ZIP tests passed.")


if __name__ == "__main__":
    main()
