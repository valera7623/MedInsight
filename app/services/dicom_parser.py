"""DICOM parsing: metadata extraction and pixel data → PNG conversion."""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class DicomParseError(Exception):
    pass


def _require_pydicom():
    try:
        import pydicom  # noqa: F401
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise DicomParseError("pydicom, numpy and Pillow are required for DICOM support") from exc


def _safe_str(value: Any, max_len: int = 255) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_len] if text else None


def _parse_dicom_date(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10].replace("-", ""), "%Y%m%d")
        except ValueError:
            continue
    return None


class DicomParser:
    def validate_dicom(self, file_path: str) -> bool:
        try:
            _require_pydicom()
            import pydicom

            ds = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
            return bool(getattr(ds, "SOPClassUID", None) or getattr(ds, "StudyInstanceUID", None))
        except Exception as exc:  # noqa: BLE001
            logger.debug("DICOM validation failed for %s: %s", file_path, exc)
            return False

    def extract_metadata(self, dicom: Any) -> dict[str, Any]:
        modality = _safe_str(getattr(dicom, "Modality", None), 16)
        body_part = _safe_str(getattr(dicom, "BodyPartExamined", None), 128)
        study_uid = _safe_str(getattr(dicom, "StudyInstanceUID", None), 128)
        series_uid = _safe_str(getattr(dicom, "SeriesInstanceUID", None), 128)
        instance_uid = _safe_str(getattr(dicom, "SOPInstanceUID", None), 128)
        if not study_uid:
            raise DicomParseError("Missing StudyInstanceUID")
        if not series_uid:
            series_uid = f"{study_uid}.1"
        if not instance_uid:
            instance_uid = f"{series_uid}.1"

        pixel_spacing = None
        if hasattr(dicom, "PixelSpacing") and dicom.PixelSpacing is not None:
            try:
                pixel_spacing = {"row": float(dicom.PixelSpacing[0]), "col": float(dicom.PixelSpacing[1])}
            except Exception:  # noqa: BLE001
                pixel_spacing = None

        return {
            "patient_name": _safe_str(getattr(dicom, "PatientName", None)),
            "patient_id": _safe_str(getattr(dicom, "PatientID", None), 128),
            "study_uid": study_uid,
            "study_date": _parse_dicom_date(getattr(dicom, "StudyDate", None)),
            "study_description": _safe_str(getattr(dicom, "StudyDescription", None), 500),
            "series_uid": series_uid,
            "series_number": int(getattr(dicom, "SeriesNumber", 1) or 1),
            "series_description": _safe_str(getattr(dicom, "SeriesDescription", None), 500),
            "instance_uid": instance_uid,
            "modality": modality,
            "body_part": body_part,
            "bit_depth": int(getattr(dicom, "BitsStored", 8) or 8),
            "pixel_spacing": pixel_spacing,
            "num_frames": int(getattr(dicom, "NumberOfFrames", 1) or 1),
        }

    def extract_pixel_data(self, dicom: Any, *, window_center: float | None = None, window_width: float | None = None) -> bytes:
        frames = self.extract_all_frames(dicom, window_center=window_center, window_width=window_width)
        if not frames:
            raise DicomParseError("No pixel data in DICOM file")
        return frames[0]

    def extract_all_frames(
        self,
        dicom: Any,
        *,
        window_center: float | None = None,
        window_width: float | None = None,
        thumbnail: bool = False,
    ) -> list[bytes]:
        _require_pydicom()
        import numpy as np
        from PIL import Image
        from pydicom.pixel_data_handlers.util import apply_voi_lut

        if not hasattr(dicom, "pixel_array"):
            raise DicomParseError("DICOM file has no pixel data")

        arr = dicom.pixel_array
        num_frames = int(getattr(dicom, "NumberOfFrames", 1) or 1)
        if arr.ndim == 2:
            arrays = [arr]
        elif arr.ndim == 3 and num_frames > 1 and arr.shape[0] == num_frames:
            arrays = [arr[i] for i in range(num_frames)]
        elif arr.ndim == 3:
            arrays = [arr[i] for i in range(arr.shape[0])]
        else:
            arrays = [arr]

        wc = window_center
        ww = window_width
        if wc is None and hasattr(dicom, "WindowCenter"):
            try:
                wc = float(dicom.WindowCenter[0] if isinstance(dicom.WindowCenter, (list, tuple)) else dicom.WindowCenter)
            except Exception:  # noqa: BLE001
                wc = None
        if ww is None and hasattr(dicom, "WindowWidth"):
            try:
                ww = float(dicom.WindowWidth[0] if isinstance(dicom.WindowWidth, (list, tuple)) else dicom.WindowWidth)
            except Exception:  # noqa: BLE001
                ww = None

        pngs: list[bytes] = []
        for frame in arrays:
            data = apply_voi_lut(frame, dicom) if hasattr(dicom, "PixelData") else frame
            data = np.asarray(data, dtype=np.float64)
            if wc is not None and ww is not None and ww > 0:
                low = wc - ww / 2
                high = wc + ww / 2
                data = np.clip(data, low, high)
                data = (data - low) / max(high - low, 1)
            else:
                data = data - np.min(data)
                denom = max(float(np.max(data)), 1.0)
                data = data / denom
            img_arr = (data * 255.0).astype(np.uint8)
            if img_arr.ndim == 2:
                mode = "L"
            else:
                img_arr = img_arr[..., 0] if img_arr.shape[-1] == 1 else img_arr
                mode = "L" if img_arr.ndim == 2 else "RGB"
            img = Image.fromarray(img_arr, mode=mode)
            if thumbnail:
                img = self._maybe_thumbnail(img)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            pngs.append(buf.getvalue())
        return pngs

    def _maybe_thumbnail(self, img: Any) -> Any:
        from PIL import Image

        if not settings.DICOM_THUMBNAIL_SIZE:
            return img
        try:
            w, h = settings.DICOM_THUMBNAIL_SIZE.lower().split("x")
            max_size = (int(w), int(h))
        except Exception:  # noqa: BLE001
            return img
        if img.width <= max_size[0] and img.height <= max_size[1]:
            return img
        copy = img.copy()
        copy.thumbnail(max_size, Image.Resampling.LANCZOS)
        return copy

    def parse_dicom_file(self, file_path: str) -> dict[str, Any]:
        _require_pydicom()
        import pydicom

        path = Path(file_path)
        if not path.exists():
            raise DicomParseError(f"File not found: {file_path}")

        ds = pydicom.dcmread(str(path), force=True)
        meta = self.extract_metadata(ds)
        png_frames = self.extract_all_frames(ds)
        if not png_frames:
            raise DicomParseError("Could not extract frames from DICOM")

        width, height = None, None
        try:
            if hasattr(ds, "pixel_array"):
                arr = ds.pixel_array
                if arr.ndim >= 2:
                    height, width = int(arr.shape[-2]), int(arr.shape[-1])
        except Exception:  # noqa: BLE001
            pass

        frames = []
        for idx, png in enumerate(png_frames):
            uid = meta["instance_uid"]
            if len(png_frames) > 1:
                uid = f"{meta['instance_uid']}.{idx}"
            frames.append(
                {
                    "instance_uid": uid,
                    "frame_number": idx,
                    "png_bytes": png,
                    "width": width,
                    "height": height,
                    "bit_depth": meta.get("bit_depth"),
                    "pixel_spacing": meta.get("pixel_spacing"),
                }
            )

        return {
            **meta,
            "frames": frames,
            "num_instances": len(frames),
        }
