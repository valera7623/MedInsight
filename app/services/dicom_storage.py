"""DICOM file and frame storage on disk."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import settings
from app.services.encryption import encrypt_bytes, encrypt_file

logger = logging.getLogger(__name__)


class DicomStorage:
    def __init__(self, base_path: str | None = None) -> None:
        self.base = Path(base_path or settings.DICOM_STORAGE_PATH)

    def study_dir(self, patient_id: int, study_uid: str) -> Path:
        safe_uid = study_uid.replace("/", "_").replace("\\", "_")
        path = self.base / str(patient_id) / safe_uid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def frames_dir(self, patient_id: int, study_uid: str) -> Path:
        path = self.study_dir(patient_id, study_uid) / "frames"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def store_encrypted(
        self,
        file_path: str,
        *,
        tenant_id: int,
        patient_id: int,
        study_uid: str,
        filename: str,
    ) -> str:
        """Encrypt original DICOM and return stored path."""
        src = Path(file_path)
        enc_path, _ = encrypt_bytes(
            src.read_bytes(),
            tenant_id,
            patient_id,
            f"dicom_{study_uid}_{Path(filename).name}",
        )
        return enc_path

    def store_frames(
        self,
        *,
        patient_id: int,
        study_uid: str,
        frames: list[tuple[str, int, bytes]],
    ) -> list[str]:
        """Save PNG frames. frames: list of (instance_uid, frame_number, png_bytes)."""
        out_dir = self.frames_dir(patient_id, study_uid)
        paths: list[str] = []
        for instance_uid, frame_number, png_bytes in frames:
            safe_uid = instance_uid.replace("/", "_").replace("\\", "_")
            name = f"{safe_uid}_f{frame_number}.png"
            dest = out_dir / name
            dest.write_bytes(png_bytes)
            paths.append(str(dest))
        return paths

    def get_study_path(self, patient_id: int, study_uid: str) -> str:
        return str(self.study_dir(patient_id, study_uid))

    def get_frame_path(self, patient_id: int, study_uid: str, instance_uid: str, frame_number: int = 0) -> str | None:
        out_dir = self.frames_dir(patient_id, study_uid)
        safe_uid = instance_uid.replace("/", "_").replace("\\", "_")
        candidate = out_dir / f"{safe_uid}_f{frame_number}.png"
        if candidate.exists():
            return str(candidate)
        matches = list(out_dir.glob(f"{safe_uid}*.png"))
        return str(matches[0]) if matches else None

    def delete_study(self, patient_id: int, study_uid: str) -> bool:
        path = self.study_dir(patient_id, study_uid)
        if not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=True)
        return True

    def temp_upload_path(self, suffix: str = ".dcm") -> Path:
        tmp = self.base / "_uploads"
        tmp.mkdir(parents=True, exist_ok=True)
        import uuid

        return tmp / f"{uuid.uuid4().hex}{suffix}"
