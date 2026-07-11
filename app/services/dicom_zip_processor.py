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
SUPPORTED_ARCHIVE_SUFFIXES = frozenset({".zip", ".7z"})
SKIP_EXTENSIONS = frozenset({
    ".txt", ".xml", ".json", ".html", ".htm", ".pdf", ".jpg", ".jpeg", ".png",
    ".gif", ".bmp", ".md", ".csv", ".ini", ".cfg", ".exe", ".dll", ".bat",
    ".zip", ".7z", ".rar", ".tar", ".gz", ".log", ".sql", ".db", ".sqlite",
})
SKIP_BASENAMES = frozenset({
    "dicomdir", "lockfile", "readme", "thorium.html", "index.htm", "autorun.inf",
})


class DicomZipError(Exception):
    pass


def _parse_dicom_file_worker(file_path: str) -> dict[str, Any] | None:
    """Parse one DICOM file (picklable for ProcessPoolExecutor)."""
    parser = DicomParser()
    try:
        parsed = parser.parse_dicom_file(file_path)
        parsed["source_filename"] = Path(file_path).name
        return parsed
    except DicomParseError as exc:
        logger.warning("Parse failed %s: %s", file_path, exc)
        return None


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
        return self._is_dicom_candidate_name(name)

    def _is_dicom_candidate_name(self, name: str) -> bool:
        """Accept .dcm/.dicom and extensionless files (common in PACS/Siemens exports)."""
        basename = Path(name).name
        if not basename or basename.startswith("."):
            return False
        if basename.lower() in SKIP_BASENAMES:
            return False
        suffix = Path(name).suffix.lower()
        if suffix in DICOM_EXTENSIONS:
            return True
        if suffix in SKIP_EXTENSIONS:
            return False
        return True

    @staticmethod
    def _file_has_dicom_preamble(path: Path) -> bool:
        try:
            with path.open("rb") as fh:
                preamble = fh.read(132)
            return len(preamble) >= 132 and preamble[128:132] == b"DICM"
        except OSError:
            return False

    def _is_probable_dicom_file(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.name.lower() in SKIP_BASENAMES:
            return False
        suffix = path.suffix.lower()
        if suffix in DICOM_EXTENSIONS:
            return True
        if suffix in SKIP_EXTENSIONS:
            return False
        if self._file_has_dicom_preamble(path):
            return True
        try:
            import pydicom

            pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _max_zip_bytes(self) -> int:
        return settings.DICOM_ZIP_MAX_SIZE_MB * 1024 * 1024

    def validate_zip(self, zip_path: str) -> bool:
        """Return True if archive contains at least one DICOM file and passes safety checks."""
        return self.validate_archive(zip_path)

    def validate_archive(self, archive_path: str) -> bool:
        try:
            self._scan_archive_entries(archive_path)
            return True
        except DicomZipError:
            return False

    def _archive_suffix(self, archive_path: str) -> str:
        suffix = Path(archive_path).suffix.lower()
        if suffix not in SUPPORTED_ARCHIVE_SUFFIXES:
            raise DicomZipError(f"Unsupported archive format: {suffix or '(none)'}")
        return suffix

    def _scan_archive_entries(self, archive_path: str, *, integrity_check: bool = True) -> list[str]:
        suffix = self._archive_suffix(archive_path)
        if suffix == ".zip":
            return [e.filename for e in self._scan_zip_entries(archive_path, integrity_check=integrity_check)]
        return self._scan_7z_entries(archive_path)

    def _check_archive_size_limits(
        self, path: Path, dicom_names: list[str], total_uncompressed: int
    ) -> None:
        if len(dicom_names) > settings.DICOM_ZIP_MAX_FILES:
            raise DicomZipError(f"Too many DICOM files (max {settings.DICOM_ZIP_MAX_FILES})")
        compressed = path.stat().st_size
        if compressed > 0 and total_uncompressed > compressed * 200:
            raise DicomZipError("Archive compression ratio suspicious (zip bomb?)")
        if total_uncompressed > self._max_zip_bytes() * 4:
            raise DicomZipError("Uncompressed size exceeds safety limit")

    def _scan_zip_entries(self, zip_path: str, *, integrity_check: bool = True) -> list[zipfile.ZipInfo]:
        path = Path(zip_path)
        if not path.is_file():
            raise DicomZipError(f"ZIP not found: {zip_path}")

        if path.stat().st_size > self._max_zip_bytes():
            raise DicomZipError(f"ZIP exceeds {settings.DICOM_ZIP_MAX_SIZE_MB} MB limit")

        dicom_entries: list[zipfile.ZipInfo] = []
        total_uncompressed = 0

        try:
            with zipfile.ZipFile(path, "r") as zf:
                if integrity_check and zf.testzip() is not None:
                    raise DicomZipError("Corrupt ZIP archive")

                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    if not self._is_safe_zip_member(info.filename):
                        logger.warning("Skipping unsafe ZIP path: %s", info.filename)
                        continue
                    if not self._is_dicom_candidate_name(info.filename):
                        continue

                    dicom_entries.append(info)
                    total_uncompressed += info.file_size

                self._check_archive_size_limits(
                    path, [e.filename for e in dicom_entries], total_uncompressed
                )

        except zipfile.BadZipFile as exc:
            raise DicomZipError("Invalid ZIP file") from exc

        if not dicom_entries:
            raise DicomZipError("ZIP contains no DICOM files")

        return dicom_entries

    def _scan_7z_entries(self, archive_path: str) -> list[str]:
        try:
            import py7zr
        except ImportError as exc:
            raise DicomZipError("py7zr is required for .7z archives") from exc

        path = Path(archive_path)
        if not path.is_file():
            raise DicomZipError(f"7z archive not found: {archive_path}")

        if path.stat().st_size > self._max_zip_bytes():
            raise DicomZipError(f"Archive exceeds {settings.DICOM_ZIP_MAX_SIZE_MB} MB limit")

        dicom_names: list[str] = []
        total_uncompressed = 0

        try:
            with py7zr.SevenZipFile(archive_path, mode="r") as zf:
                for info in zf.list():
                    if info.is_directory:
                        continue
                    name = info.filename
                    if not self._is_safe_zip_member(name):
                        logger.warning("Skipping unsafe 7z path: %s", name)
                        continue
                    if not self._is_dicom_candidate_name(name):
                        continue
                    dicom_names.append(name)
                    total_uncompressed += int(info.uncompressed or 0)

                self._check_archive_size_limits(path, dicom_names, total_uncompressed)
        except py7zr.Bad7zFile as exc:
            raise DicomZipError("Invalid 7z archive") from exc
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, DicomZipError):
                raise
            raise DicomZipError(f"Failed to read 7z archive: {exc}") from exc

        if not dicom_names:
            raise DicomZipError("7z archive contains no DICOM files")

        return dicom_names

    def extract_zip(self, zip_path: str) -> str:
        """Extract archive to a new temp directory; returns directory path."""
        return self.extract_archive(zip_path)

    def extract_archive(self, archive_path: str, *, integrity_check: bool = False) -> str:
        suffix = self._archive_suffix(archive_path)
        if suffix == ".zip":
            return self._extract_zip(archive_path, integrity_check=integrity_check)
        return self._extract_7z(archive_path)

    def _extract_zip(self, zip_path: str, *, integrity_check: bool = False) -> str:
        entries = self._scan_zip_entries(zip_path, integrity_check=integrity_check)
        dest = self.temp_root / uuid.uuid4().hex
        dest.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in entries:
                safe_name = Path(info.filename).name
                target = dest / safe_name
                if target.exists():
                    target = dest / f"{uuid.uuid4().hex[:8]}_{safe_name}"
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        return str(dest)

    def _extract_7z(self, archive_path: str) -> str:
        try:
            import py7zr
        except ImportError as exc:
            raise DicomZipError("py7zr is required for .7z archives") from exc

        dest = self.temp_root / uuid.uuid4().hex
        dest.mkdir(parents=True, exist_ok=True)

        with py7zr.SevenZipFile(archive_path, mode="r") as zf:
            zf.extractall(path=dest)

        return str(dest)

    def scan_files(self, directory: str) -> list[str]:
        """Return DICOM file paths under directory (recursive), including extensionless."""
        root = Path(directory)
        if not root.is_dir():
            return []
        files: list[str] = []
        for path in sorted(root.rglob("*")):
            if self._is_probable_dicom_file(path):
                files.append(str(path))
        return files

    def iter_zip_dicom_paths(self, zip_path: str) -> list[tuple[str, str]]:
        """List (archive_internal_name, display_filename) without full extraction."""
        return self.iter_archive_dicom_paths(zip_path)

    def iter_archive_dicom_paths(
        self, archive_path: str, *, integrity_check: bool | None = None
    ) -> list[tuple[str, str]]:
        if integrity_check is None:
            integrity_check = settings.DICOM_ZIP_INTEGRITY_CHECK
        names = self._scan_archive_entries(archive_path, integrity_check=integrity_check)
        return [(name, Path(name).name) for name in names]

    def group_files(self, files: list[str]) -> dict[str, dict[str, list[str]]]:
        """Group file paths by study_uid → series_uid in a single metadata read per file."""
        groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for file_path in files:
            uids = self._read_file_uids(file_path)
            groups[uids["study_uid"]][uids["series_uid"]].append(file_path)
        return {study_uid: dict(series_map) for study_uid, series_map in groups.items()}

    def group_by_study(self, files: list[str]) -> dict[str, list[str]]:
        """Group file paths by StudyInstanceUID."""
        groups: dict[str, list[str]] = defaultdict(list)
        for study_uid, series_map in self.group_files(files).items():
            for series_files in series_map.values():
                groups[study_uid].extend(series_files)
        return dict(groups)

    def group_by_series(self, files: list[str]) -> dict[str, list[str]]:
        """Group file paths by SeriesInstanceUID."""
        groups: dict[str, list[str]] = defaultdict(list)
        for file_path in files:
            uids = self._read_file_uids(file_path)
            groups[uids["series_uid"]].append(file_path)
        return dict(groups)

    def _read_file_uids(self, file_path: str) -> dict[str, str]:
        try:
            import pydicom

            ds = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
            study_uid = getattr(ds, "StudyInstanceUID", None)
            series_uid = getattr(ds, "SeriesInstanceUID", None)
            if study_uid and series_uid:
                return {"study_uid": str(study_uid), "series_uid": str(series_uid)}
            if study_uid:
                return {
                    "study_uid": str(study_uid),
                    "series_uid": f"{study_uid}.series.{uuid.uuid4().hex[:8]}",
                }
        except Exception as exc:  # noqa: BLE001
            logger.debug("UID read failed %s: %s", file_path, exc)
        study = f"unknown-study-{uuid.uuid4().hex}"
        return {"study_uid": study, "series_uid": f"{study}.series.{uuid.uuid4().hex[:8]}"}

    def _read_study_uid(self, file_path: str) -> str:
        return self._read_file_uids(file_path)["study_uid"]

    def _read_series_uid(self, file_path: str) -> str:
        return self._read_file_uids(file_path)["series_uid"]

    def process_study(
        self,
        files: list[str],
        patient_id: int,
        *,
        series_groups: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """
        Parse grouped files into study structure (no DB writes).

        Returns dict with study_uid, series list, total_instances, metadata.
        """
        if not files:
            raise DicomZipError("No DICOM files to process")

        if series_groups is None:
            series_groups = self.group_by_series(files)

        parsed_series: list[dict[str, Any]] = []
        study_meta: dict[str, Any] | None = None
        total_instances = 0

        for series_uid, series_files in series_groups.items():
            series_parsed: list[dict[str, Any]] = []
            series_meta: dict[str, Any] | None = None

            workers = settings.DICOM_ZIP_PARSE_WORKERS
            if workers > 1 and len(series_files) > 1:
                from concurrent.futures import ProcessPoolExecutor, as_completed

                with ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_parse_dicom_file_worker, fp): fp for fp in series_files}
                    for future in as_completed(futures):
                        parsed = future.result()
                        if not parsed:
                            continue
                        series_parsed.append(parsed)
                        if study_meta is None:
                            study_meta = parsed
                        if series_meta is None:
                            series_meta = parsed
                        total_instances += parsed.get("num_instances", len(parsed.get("frames", [])))
            else:
                for file_path in series_files:
                    parsed = _parse_dicom_file_worker(file_path)
                    if not parsed:
                        continue
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
