"""DICOM ZIP archive extraction, validation and grouping."""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.dicom_parser import DicomParser, DicomParseError

logger = logging.getLogger(__name__)

DICOM_EXTENSIONS = {".dcm", ".dicom"}


class DicomZipError(Exception):
    pass


class DicomZipProcessor:
    """Process ZIP archives containing multiple DICOM files."""

    def __init__(self, parser: DicomParser | None = None) -> None:
        self.parser = parser or DicomParser()
        self.temp_root = Path(settings.DICOM_ZIP_TEMP_DIR)
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def _is_safe_zip_member(self, name: str) -> bool:
        normalized = Path(name)
        if normalized.is_absolute() or ".." in normalized.parts:
            return False
        return True

    def _is_dicom_name(self, name: str) -> bool:
        return Path(name).suffix.lower() in DICOM_EXTENSIONS

    def _max_zip_bytes(self) -> int:
        return settings.DICOM_ZIP_MAX_SIZE_MB * 1024 * 1024

    def validate_zip(self, zip_path: str) -> bool:
        """Return True if archive contains at least one DICOM file and passes safety checks."""
        try:
            self._scan_zip_entries(zip_path)
            return True
        except DicomZipError:
            return False

    def _scan_zip_entries(self, zip_path: str) -> list[zipfile.ZipInfo]:
        path = Path(zip_path)
        if not path.is_file():
            raise DicomZipError(f"ZIP not found: {zip_path}")

        if path.stat().st_size > self._max_zip_bytes():
            raise DicomZipError(f"ZIP exceeds {settings.DICOM_ZIP_MAX_SIZE_MB} MB limit")

        dicom_entries: list[zipfile.ZipInfo] = []
        total_uncompressed = 0

        try:
            with zipfile.ZipFile(path, "r") as zf:
                if zf.testzip() is not None:
                    raise DicomZipError("Corrupt ZIP archive")

                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    if not self._is_safe_zip_member(info.filename):
                        logger.warning("Skipping unsafe ZIP path: %s", info.filename)
                        continue
                    if not self._is_dicom_name(info.filename):
                        continue

                    dicom_entries.append(info)
                    total_uncompressed += info.file_size

                    if len(dicom_entries) > settings.DICOM_ZIP_MAX_FILES:
                        raise DicomZipError(
                            f"Too many DICOM files (max {settings.DICOM_ZIP_MAX_FILES})"
                        )

                # Zip-bomb guard: uncompressed total vs compressed size
                compressed = path.stat().st_size
                if compressed > 0 and total_uncompressed > compressed * 200:
                    raise DicomZipError("ZIP compression ratio suspicious (zip bomb?)")

                if total_uncompressed > self._max_zip_bytes() * 4:
                    raise DicomZipError("Uncompressed size exceeds safety limit")

        except zipfile.BadZipFile as exc:
            raise DicomZipError("Invalid ZIP file") from exc

        if not dicom_entries:
            raise DicomZipError("ZIP contains no .dcm files")

        return dicom_entries

    def extract_zip(self, zip_path: str) -> str:
        """Extract archive to a new temp directory; returns directory path."""
        entries = self._scan_zip_entries(zip_path)
        dest = self.temp_root / uuid.uuid4().hex
        dest.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in entries:
                safe_name = Path(info.filename).name
                target = dest / safe_name
                # Handle duplicate basenames
                if target.exists():
                    target = dest / f"{uuid.uuid4().hex[:8]}_{safe_name}"
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        return str(dest)

    def scan_files(self, directory: str) -> list[str]:
        """Return all .dcm paths under directory (recursive)."""
        root = Path(directory)
        if not root.is_dir():
            return []
        files: list[str] = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in DICOM_EXTENSIONS:
                files.append(str(path))
        return files

    def iter_zip_dicom_paths(self, zip_path: str) -> list[tuple[str, str]]:
        """List (zip_internal_name, display_filename) without full extraction."""
        entries = self._scan_zip_entries(zip_path)
        return [(e.filename, Path(e.filename).name) for e in entries]

    def group_by_study(self, files: list[str]) -> dict[str, list[str]]:
        """Group file paths by StudyInstanceUID."""
        groups: dict[str, list[str]] = defaultdict(list)
        for file_path in files:
            study_uid = self._read_study_uid(file_path)
            groups[study_uid].append(file_path)
        return dict(groups)

    def group_by_series(self, files: list[str]) -> dict[str, list[str]]:
        """Group file paths by SeriesInstanceUID."""
        groups: dict[str, list[str]] = defaultdict(list)
        for file_path in files:
            series_uid = self._read_series_uid(file_path)
            groups[series_uid].append(file_path)
        return dict(groups)

    def _read_study_uid(self, file_path: str) -> str:
        try:
            import pydicom

            ds = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
            uid = getattr(ds, "StudyInstanceUID", None)
            if uid:
                return str(uid)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Study UID read failed %s: %s", file_path, exc)
        return f"unknown-study-{uuid.uuid4().hex}"

    def _read_series_uid(self, file_path: str) -> str:
        try:
            import pydicom

            ds = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
            uid = getattr(ds, "SeriesInstanceUID", None)
            if uid:
                return str(uid)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Series UID read failed %s: %s", file_path, exc)
        study = self._read_study_uid(file_path)
        return f"{study}.series.{uuid.uuid4().hex[:8]}"

    def process_study(self, files: list[str], patient_id: int) -> dict[str, Any]:
        """
        Parse grouped files into study structure (no DB writes).

        Returns dict with study_uid, series list, total_instances, metadata.
        """
        if not files:
            raise DicomZipError("No DICOM files to process")

        series_groups = self.group_by_series(files)
        parsed_series: list[dict[str, Any]] = []
        study_meta: dict[str, Any] | None = None
        total_instances = 0

        for series_uid, series_files in series_groups.items():
            series_parsed: list[dict[str, Any]] = []
            series_meta: dict[str, Any] | None = None

            for file_path in series_files:
                if not self.parser.validate_dicom(file_path):
                    logger.warning("Skipping invalid DICOM: %s", file_path)
                    continue
                try:
                    parsed = self.parser.parse_dicom_file(file_path)
                except DicomParseError as exc:
                    logger.warning("Parse failed %s: %s", file_path, exc)
                    continue

                parsed["source_filename"] = Path(file_path).name
                series_parsed.append(parsed)
                if study_meta is None:
                    study_meta = parsed
                if series_meta is None:
                    series_meta = parsed
                total_instances += parsed.get("num_instances", len(parsed.get("frames", [])))

            if series_parsed:
                parsed_series.append(
                    {
                        "series_uid": series_uid,
                        "series_number": series_meta.get("series_number") if series_meta else None,
                        "series_description": series_meta.get("series_description") if series_meta else None,
                        "modality": series_meta.get("modality") if series_meta else None,
                        "original_filename": Path(series_files[0]).name if series_files else None,
                        "instances": series_parsed,
                    }
                )

        if not study_meta or not parsed_series:
            raise DicomZipError("No valid DICOM instances in archive")

        return {
            "patient_id": patient_id,
            "study_uid": study_meta["study_uid"],
            "study_date": study_meta.get("study_date"),
            "study_description": study_meta.get("study_description"),
            "modality": study_meta.get("modality"),
            "body_part": study_meta.get("body_part"),
            "patient_name": study_meta.get("patient_name"),
            "patient_id_dicom": study_meta.get("patient_id"),
            "num_series": len(parsed_series),
            "num_instances": total_instances,
            "series": parsed_series,
        }

    def cleanup_temp(self, directory: str) -> None:
        path = Path(directory)
        if path.exists() and path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    def temp_zip_path(self, suffix: str = ".zip") -> Path:
        self.temp_root.mkdir(parents=True, exist_ok=True)
        return self.temp_root / f"{uuid.uuid4().hex}{suffix}"
