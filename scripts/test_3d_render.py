#!/usr/bin/env python3
"""Test 3D volume reconstruction and MPR rendering."""

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
os.environ["DICOM_3D_ENABLED"] = "true"
os.environ["ENCRYPTION_ENABLED"] = "false"
_dicom_dir = tempfile.mkdtemp(prefix="medinsight_3d_test_")
os.environ["DICOM_STORAGE_PATH"] = _dicom_dir


def _make_slice_dicom(path: Path, study_uid: str, series_uid: str, instance: int, z: int) -> None:
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
    ds.PatientName = "Volume^Test"
    ds.PatientID = "VOL001"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.Modality = "CT"
    ds.StudyDate = "20240615"
    ds.SeriesNumber = 1
    ds.InstanceNumber = instance
    ds.PixelSpacing = [0.5, 0.5]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 32
    ds.Columns = 32
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.WindowCenter = 128
    ds.WindowWidth = 256

    base = np.linspace(0, 255, 32 * 32, dtype=np.uint16).reshape(32, 32)
    base = base + z * 10
    ds.PixelData = np.clip(base, 0, 4095).astype(np.uint16).tobytes()
    ds.save_as(str(path))


def _bootstrap_study_with_slices(num_slices: int = 8) -> str:
    from pydicom.uid import generate_uid

    from app.database import Base, SessionLocal, engine
    from app.models import DicomFrame, DicomSeries, DicomStudy, Patient, Tenant, User
    from app.services.dicom_parser import DicomParser
    from app.services.dicom_storage import DicomStorage

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    tenant = Tenant(name="Test", subdomain="test3d")
    db.add(tenant)
    db.flush()

    user = User(
        email="vol3d@test.com",
        hashed_password="x",
        tenant_id=tenant.id,
        role="doctor",
    )
    db.add(user)
    db.flush()

    patient = Patient(
        tenant_id=tenant.id,
        first_name="Vol",
        last_name="Test",
        birth_date="1990-01-01",
        gender="M",
    )
    db.add(patient)
    db.flush()

    study_uid = generate_uid()
    series_uid = generate_uid()
    study = DicomStudy(
        patient_id=patient.id,
        tenant_id=tenant.id,
        user_id=user.id,
        study_uid=study_uid,
        status="ready",
        modality="CT",
        num_series=1,
        num_instances=num_slices,
    )
    db.add(study)
    db.flush()

    series = DicomSeries(
        study_id=study.id,
        series_uid=series_uid,
        series_number=1,
        modality="CT",
        num_instances=num_slices,
    )
    db.add(series)
    db.flush()

    parser = DicomParser()
    storage = DicomStorage()
    tmp = Path(tempfile.mkdtemp())

    for i in range(num_slices):
        dcm_path = tmp / f"slice_{i:03d}.dcm"
        _make_slice_dicom(dcm_path, study_uid, series_uid, i + 1, i)
        parsed = parser.parse_dicom_file(str(dcm_path))
        frame = parsed["frames"][0]
        uid = f"{parsed['instance_uid']}.{i}"
        paths = storage.store_frames(
            patient_id=patient.id,
            study_uid=study_uid,
            frames=[(uid, i, frame["png_bytes"])],
        )
        db.add(
            DicomFrame(
                series_id=series.id,
                instance_uid=uid,
                frame_number=i,
                image_path=paths[0],
                width=32,
                height=32,
                bit_depth=16,
                pixel_spacing={"row": 0.5, "col": 0.5},
            )
        )

    db.commit()
    db.close()
    return study_uid


def test_volume_build_and_mpr() -> None:
    from app.database import SessionLocal
    from app.services.dicom_volume import DicomVolumeService

    study_uid = _bootstrap_study_with_slices(8)
    db = SessionLocal()
    try:
        service = DicomVolumeService(db)
        info = service.get_volume_info(study_uid)
        assert info["num_slices"] == 8
        assert info["dimensions"] == [8, 32, 32]

        packed = service.build_volume_from_frames(study_uid)
        assert len(packed) > 100

        cached_info = service.get_volume_info(study_uid)
        assert cached_info["cached"] is True

        for plane in ("axial", "coronal", "sagittal"):
            png = service.render_mpr(study_uid, plane, 4, {"preset": "brain"})
            assert png[:8] == b"\x89PNG\r\n\x1a\n", f"{plane} MPR failed"

        vr_png = service.render_volume(study_uid, {"preset": "bone", "mode": "mip", "azimuth": 15})
        assert vr_png[:8] == b"\x89PNG\r\n\x1a\n"

        print("OK: volume build, MPR and 3D render produce valid PNG")
    finally:
        db.close()


def test_celery_task_sync() -> None:
    from app.tasks.dicom_volume_task import build_volume_from_study

    study_uid = _bootstrap_study_with_slices(6)
    result = build_volume_from_study(study_uid)
    assert result["status"] == "ready"
    assert result["dimensions"] == [6, 32, 32]
    print("OK: Celery task build_volume_from_study")


if __name__ == "__main__":
    test_volume_build_and_mpr()
    test_celery_task_sync()
    print("All 3D render tests passed.")
