"""3D volume reconstruction, MPR and volume rendering for DICOM studies."""

from __future__ import annotations

import base64
import io
import json
import logging
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import SessionLocal
from app.models import DicomFrame, DicomSeries, DicomStudy
from app.services.dicom_storage import DicomStorage

logger = logging.getLogger(__name__)

INSUFFICIENT_SLICES_CODE = "insufficient_slices"
INSUFFICIENT_SLICES_MESSAGE = (
    "Недостаточно срезов для 3D: в выбранной серии {count} кадр(ов), нужно минимум 2. "
    "Откройте исследование в 2D или загрузите полный том (ZIP с множеством .dcm)."
)

PLANES = frozenset({"axial", "coronal", "sagittal"})

# In-process volume cache — avoids Redis decompress on every MPR/render in the same worker.
_mem_volume_cache: dict[str, tuple[np.ndarray, dict[str, Any]]] = {}
_mem_volume_cache_max = 4

# Window/level presets for PNG-derived volumes (0–255 grayscale).
# HU-based values (e.g. lung WC=-600) do not apply — frames are pre-converted to PNG.
WINDOW_PRESETS: dict[str, dict[str, float]] = {
    "default": {"window_center": 128.0, "window_width": 256.0},
    "lung": {"window_center": 90.0, "window_width": 360.0},
    "bone": {"window_center": 210.0, "window_width": 100.0},
    "brain": {"window_center": 128.0, "window_width": 72.0},
    "abdomen": {"window_center": 130.0, "window_width": 180.0},
    "liver": {"window_center": 140.0, "window_width": 110.0},
}

# Optional W/L tweak per projection mode (still on 0–255 scale).
_MODE_PRESET_TUNING: dict[tuple[str, str], dict[str, float]] = {
    ("lung", "minip"): {"window_center": 70.0, "window_width": 320.0},
    ("lung", "mip"): {"window_center": 110.0, "window_width": 280.0},
    ("bone", "mip"): {"window_center": 220.0, "window_width": 80.0},
}

# Prefer diagnostic cross-sectional series over segmentation / secondary objects.
_MODALITY_PRIORITY: dict[str, int] = {
    "CT": 100,
    "MR": 90,
    "PT": 80,
    "NM": 70,
    "US": 50,
    "XA": 40,
    "CR": 35,
    "DX": 35,
    "SEG": 5,
    "RTSTRUCT": 5,
    "RT": 5,
    "REG": 10,
    "SR": 0,
    "DOC": 0,
    "KO": 0,
    "PR": 0,
}

_NON_VOLUMETRIC_MODALITIES = frozenset(
    {"SEG", "RTSTRUCT", "RT", "REG", "SR", "DOC", "KO", "PR"}
)


class DicomVolumeError(Exception):
    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code


def _redis_binary():
    import redis

    return redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=False,
    )


def _volume_cache_key(study_uid: str, suffix: str) -> str:
    return f"volume:{study_uid}:{suffix}"


def _disk_volume_dir(patient_id: int, study_uid: str) -> Path:
    storage = DicomStorage()
    path = storage.study_dir(patient_id, study_uid) / "volume"
    path.mkdir(parents=True, exist_ok=True)
    return path


class DicomVolumeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.storage = DicomStorage()

    def _get_study(self, study_uid: str) -> DicomStudy | None:
        return (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == study_uid)
            .first()
        )

    def _select_series(self, study: DicomStudy) -> DicomSeries | None:
        if not study.series:
            return None
        candidates = [s for s in study.series if s.frames]
        if not candidates:
            return None

        def score(series: DicomSeries) -> tuple[int, int]:
            modality = (series.modality or study.modality or "").upper()
            priority = _MODALITY_PRIORITY.get(modality, 30)
            return (priority, len(series.frames))

        return max(candidates, key=score)

    def _volume_warning(self, series: DicomSeries | None, *, num_slices: int = 0) -> str | None:
        warnings: list[str] = []
        if num_slices and num_slices < 64:
            warnings.append(
                f"Мало срезов ({num_slices}): левая панель — 2D-проекция сквозь объём, "
                "не интерактивная 3D-модель. Для CT обычно ≥100 срезов. "
                "Выберите MIP или VR и вращайте мышью."
            )
        if not series:
            return warnings[0] if warnings else None
        modality = (series.modality or "").upper()
        if modality in _NON_VOLUMETRIC_MODALITIES:
            warnings.append(
                f"Серия {modality} — это не CT/MR. Пресеты Lung/Bone неприменимы; "
                "используйте Default + MIP или откройте CT-серию в 2D-вьюере."
            )
        return " ".join(warnings) if warnings else None

    def _sorted_frames(self, series: DicomSeries) -> list[DicomFrame]:
        return sorted(series.frames, key=lambda f: (f.frame_number, f.instance_uid))

    def _check_geometric_consistency(self, frames: list[DicomFrame]) -> None:
        if len(frames) < 2:
            return
        ref_w, ref_h = frames[0].width, frames[0].height
        if not ref_w or not ref_h:
            return
        for frame in frames[1:]:
            if frame.width != ref_w or frame.height != ref_h:
                raise DicomVolumeError(
                    "Frames have inconsistent dimensions — cannot build volume"
                )

    def _spacing_from_frames(self, frames: list[DicomFrame]) -> tuple[float, float, float]:
        row_sp = 1.0
        col_sp = 1.0
        if frames and frames[0].pixel_spacing:
            ps = frames[0].pixel_spacing
            row_sp = float(ps.get("row") or ps.get("Row") or 1.0)
            col_sp = float(ps.get("col") or ps.get("Column") or 1.0)
        slice_sp = max(row_sp, col_sp)
        return (slice_sp, row_sp, col_sp)

    def _load_frame_array(self, frame: DicomFrame) -> np.ndarray:
        path = Path(frame.image_path)
        if not path.exists():
            study = frame.series.study if frame.series else None
            if study:
                alt = self.storage.get_frame_path(
                    study.patient_id, study.study_uid, frame.instance_uid, frame.frame_number
                )
                if alt:
                    path = Path(alt)
        if not path.exists():
            raise DicomVolumeError(f"Frame image not found: {frame.instance_uid}")
        with Image.open(path) as img:
            gray = img.convert("L")
            return np.asarray(gray, dtype=np.float32)

    def _pack_volume(self, volume: np.ndarray) -> bytes:
        raw = volume.astype(np.float32).tobytes()
        return zlib.compress(raw, level=3)

    def _unpack_volume(self, data: bytes, info: dict[str, Any]) -> np.ndarray:
        raw = zlib.decompress(data)
        dims = info["dimensions"]
        arr = np.frombuffer(raw, dtype=np.float32)
        return arr.reshape(dims)

    def _cache_set(self, study_uid: str, volume: np.ndarray, info: dict[str, Any]) -> None:
        payload = self._pack_volume(volume)
        max_bytes = settings.DICOM_3D_MAX_VOLUME_MB * 1024 * 1024
        if len(payload) > max_bytes:
            raise DicomVolumeError(
                f"Volume exceeds DICOM_3D_MAX_VOLUME_MB ({settings.DICOM_3D_MAX_VOLUME_MB} MB)"
            )

        ttl = getattr(settings, "DICOM_3D_CACHE_TTL_SECONDS", 3600)
        info_bytes = json.dumps(info).encode("utf-8")

        try:
            client = _redis_binary()
            client.setex(_volume_cache_key(study_uid, "data"), ttl, payload)
            client.setex(_volume_cache_key(study_uid, "info"), ttl, info_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis volume cache failed for %s: %s", study_uid, exc)

        study = self._get_study(study_uid)
        if study:
            vdir = _disk_volume_dir(study.patient_id, study_uid)
            (vdir / "volume.bin").write_bytes(payload)
            (vdir / "info.json").write_text(json.dumps(info), encoding="utf-8")

    def _cache_get(self, study_uid: str) -> tuple[np.ndarray | None, dict[str, Any] | None]:
        cached = _mem_volume_cache.get(study_uid)
        if cached is not None:
            return cached[0], cached[1]

        try:
            client = _redis_binary()
            data = client.get(_volume_cache_key(study_uid, "data"))
            info_raw = client.get(_volume_cache_key(study_uid, "info"))
            if data and info_raw:
                info = json.loads(info_raw.decode("utf-8"))
                study = self._get_study(study_uid)
                if study:
                    best = self._select_series(study)
                    if best and info.get("series_uid") and info.get("series_uid") != best.series_uid:
                        return None, None
                volume = self._unpack_volume(data, info)
                self._mem_cache_put(study_uid, volume, info)
                return volume, info
        except Exception as exc:  # noqa: BLE001
            logger.debug("Redis volume cache miss for %s: %s", study_uid, exc)

        study = self._get_study(study_uid)
        if not study:
            return None, None
        vdir = _disk_volume_dir(study.patient_id, study_uid)
        data_path = vdir / "volume.bin"
        info_path = vdir / "info.json"
        if data_path.exists() and info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            study = self._get_study(study_uid)
            if study:
                best = self._select_series(study)
                if best and info.get("series_uid") and info.get("series_uid") != best.series_uid:
                    return None, None
            volume = self._unpack_volume(data_path.read_bytes(), info)
            self._mem_cache_put(study_uid, volume, info)
            return volume, info
        return None, None

    def _mem_cache_put(self, study_uid: str, volume: np.ndarray, info: dict[str, Any]) -> None:
        if len(_mem_volume_cache) >= _mem_volume_cache_max:
            _mem_volume_cache.pop(next(iter(_mem_volume_cache)))
        _mem_volume_cache[study_uid] = (volume, info)

    def is_volume_cached(self, study_uid: str) -> bool:
        volume, info = self._cache_get(study_uid)
        return volume is not None and info is not None

    def get_volume_info(self, study_uid: str) -> dict[str, Any]:
        """Return volume metadata (dimensions, spacing, orientation, cache status)."""
        _, info = self._cache_get(study_uid)
        if info:
            study = self._get_study(study_uid)
            series = self._select_series(study) if study else None
            num_slices = int(info.get("num_slices") or (info.get("dimensions") or [0])[0])
            return {
                **info,
                "cached": True,
                "status": "ready",
                "warning": self._volume_warning(series, num_slices=num_slices),
            }

        study = self._get_study(study_uid)
        if not study:
            raise DicomVolumeError("Study not found")
        if study.status != "ready":
            raise DicomVolumeError(f"Study not ready (status={study.status})")

        series = self._select_series(study)
        if not series:
            raise DicomVolumeError("No series with frames available")

        frames = self._sorted_frames(series)
        spacing = self._spacing_from_frames(frames)
        width = frames[0].width or 0
        height = frames[0].height or 0

        available = [
            {
                "series_uid": s.series_uid,
                "modality": s.modality,
                "series_description": s.series_description,
                "num_frames": len(s.frames),
            }
            for s in study.series
            if s.frames
        ]

        num_slices = len(frames)
        status = "not_built"
        error_code = None
        error_message = None
        if num_slices < 2:
            status = "unavailable"
            error_code = INSUFFICIENT_SLICES_CODE
            error_message = INSUFFICIENT_SLICES_MESSAGE.format(count=num_slices)

        return {
            "study_uid": study_uid,
            "series_uid": series.series_uid,
            "modality": series.modality or study.modality,
            "num_slices": num_slices,
            "dimensions": [num_slices, height, width],
            "spacing": list(spacing),
            "orientation": [1, 0, 0, 0, 1, 0],
            "cached": False,
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "presets": list(WINDOW_PRESETS.keys()),
            "available_series": available,
            "warning": self._volume_warning(series, num_slices=num_slices),
        }

    def get_volume_data(self, study_uid: str) -> dict[str, Any]:
        """Metadata required by the 3D frontend (includes window presets)."""
        info = self.get_volume_info(study_uid)
        volume, cached_info = self._cache_get(study_uid)
        if cached_info:
            info.update(cached_info)
            info["cached"] = True
            info["status"] = "ready"
            info["data_size_bytes"] = int(volume.nbytes) if volume is not None else 0
        return info

    def build_volume_from_frames(self, study_uid: str) -> bytes:
        """Assemble a 3D volume from stored PNG frames; returns packed bytes."""
        study = self._get_study(study_uid)
        if not study:
            raise DicomVolumeError("Study not found")
        if study.status != "ready":
            raise DicomVolumeError(f"Study not ready (status={study.status})")

        series = self._select_series(study)
        if not series:
            raise DicomVolumeError("No series with frames")

        frames = self._sorted_frames(series)
        if len(frames) < 2:
            raise DicomVolumeError(
                INSUFFICIENT_SLICES_MESSAGE.format(count=len(frames)),
                code=INSUFFICIENT_SLICES_CODE,
            )

        self._check_geometric_consistency(frames)

        workers = max(1, min(settings.DICOM_3D_FRAME_LOAD_WORKERS, len(frames)))
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                slices = list(pool.map(self._load_frame_array, frames))
        else:
            slices = [self._load_frame_array(frame) for frame in frames]

        volume = np.stack(slices, axis=0)
        spacing = self._spacing_from_frames(frames)
        z, y, x = volume.shape

        info = {
            "study_uid": study_uid,
            "series_uid": series.series_uid,
            "modality": series.modality or study.modality,
            "num_slices": z,
            "dimensions": [z, y, x],
            "spacing": list(spacing),
            "orientation": [1, 0, 0, 0, 1, 0],
            "dtype": "float32",
            "presets": list(WINDOW_PRESETS.keys()),
            "warning": self._volume_warning(series, num_slices=z),
        }

        self._mem_cache_put(study_uid, volume, info)
        self._cache_set(study_uid, volume, info)
        return self._pack_volume(volume)

    def _resolve_window(
        self, params: dict[str, Any], volume: np.ndarray
    ) -> tuple[float, float]:
        preset = (params.get("preset") or "").lower()
        mode = (params.get("mode") or "mip").lower()
        if preset and preset in WINDOW_PRESETS:
            tuning = _MODE_PRESET_TUNING.get((preset, mode))
            if tuning:
                return tuning["window_center"], tuning["window_width"]
            p = WINDOW_PRESETS[preset]
            return p["window_center"], p["window_width"]

        wc = params.get("window_center")
        ww = params.get("window_width")
        if wc is not None and ww is not None:
            return float(wc), float(ww)

        vmin, vmax = float(np.min(volume)), float(np.max(volume))
        return (vmin + vmax) / 2.0, max(vmax - vmin, 1.0)

    def _apply_window(self, data: np.ndarray, wc: float, ww: float) -> np.ndarray:
        low = wc - ww / 2.0
        high = wc + ww / 2.0
        clipped = np.clip(data, low, high)
        normalized = (clipped - low) / max(high - low, 1e-6)
        return (normalized * 255.0).astype(np.uint8)

    def _normalize_for_display(
        self,
        data: np.ndarray,
        params: dict[str, Any],
        volume: np.ndarray,
        *,
        is_projection: bool = False,
    ) -> np.ndarray:
        """Apply W/L preset or auto-stretch when contrast is too flat (common for SEG / MinIP)."""
        custom = params.get("window_center") is not None and params.get("window_width") is not None
        if custom:
            wc, ww = self._resolve_window(params, volume)
            return self._apply_window(data, wc, ww)

        std = float(np.std(data))
        dynamic = float(np.percentile(data, 98) - np.percentile(data, 2))
        mode = (params.get("mode") or "mip").lower()
        needs_auto = std < 18 or dynamic < 20 or (is_projection and mode == "minip")

        if needs_auto:
            lo = float(np.percentile(data, 1))
            hi = float(np.percentile(data, 99))
            if hi - lo < 1:
                lo, hi = float(np.min(data)), float(np.max(data))
            if hi - lo < 1:
                return np.full(data.shape, 128, dtype=np.uint8)
            normalized = (np.clip(data, lo, hi) - lo) / (hi - lo)
            return (normalized * 255.0).astype(np.uint8)

        wc, ww = self._resolve_window(params, volume)
        return self._apply_window(data, wc, ww)

    def _shaded_vr_projection(self, rotated: np.ndarray) -> np.ndarray:
        """MIP with depth shading — reads more like a 3D volume than flat MIP."""
        depth = rotated.shape[0]
        if depth < 2:
            return rotated[0]
        mip = np.max(rotated, axis=0)
        z_peak = np.argmax(rotated, axis=0).astype(np.float32)
        gy, gx = np.gradient(z_peak)
        norm = np.hypot(gx, gy) + 1e-6
        shade = 0.5 + 0.5 * (gx / norm)
        shade = np.clip(shade, 0.35, 1.0)
        return mip * shade

    def _project_volume(self, rotated: np.ndarray, mode: str) -> np.ndarray:
        mode = (mode or "mip").lower()
        if mode == "minip":
            return np.min(rotated, axis=0)
        if mode == "avg":
            return np.mean(rotated, axis=0)
        if mode == "vr":
            return self._shaded_vr_projection(rotated)
        return np.max(rotated, axis=0)

    def _slice_volume(
        self, volume: np.ndarray, plane: str, slice_index: int
    ) -> np.ndarray:
        z, y, x = volume.shape
        plane = plane.lower()
        if plane == "axial":
            idx = int(np.clip(slice_index, 0, z - 1))
            return volume[idx, :, :]
        if plane == "coronal":
            idx = int(np.clip(slice_index, 0, y - 1))
            return volume[:, idx, :]
        if plane == "sagittal":
            idx = int(np.clip(slice_index, 0, x - 1))
            return volume[:, :, idx]
        raise DicomVolumeError(f"Unknown plane: {plane}")

    def _enhance_mpr_slice(
        self,
        slab: np.ndarray,
        plane: str,
        vol_shape: tuple[int, int, int],
        spacing: tuple[float, float, float] | None = None,
    ) -> np.ndarray:
        """Upsample through-plane axis so coronal/sagittal fill the viewport."""
        if plane == "axial":
            return slab
        _z, y, _x = vol_shape
        thick = slab.shape[0]
        if thick < 2 or thick >= y:
            return slab
        sz, sy, _sx = spacing or (1.0, 1.0, 1.0)
        # Match in-plane row extent; honour slice spacing when coarser than pixels.
        target = max(y, int(round(thick * sz / max(sy, 1e-6))))
        target = min(target, 1024)
        if thick >= target:
            return slab
        return ndimage.zoom(slab, (target / thick, 1), order=1)

    def _array_to_png(self, arr: np.ndarray, *, max_edge: int | None = None) -> bytes:
        img = Image.fromarray(arr, mode="L")
        edge_limit = max_edge if max_edge is not None else settings.DICOM_3D_PREVIEW_MAX_EDGE
        if edge_limit and edge_limit > 0:
            w, h = img.size
            edge = max(w, h)
            if edge > edge_limit:
                scale = edge_limit / edge
                img = img.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    Image.Resampling.BILINEAR,
                )
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=settings.DICOM_PNG_COMPRESS_LEVEL)
        return buf.getvalue()

    def _get_volume_or_build(self, study_uid: str) -> tuple[np.ndarray, dict[str, Any]]:
        volume, info = self._cache_get(study_uid)
        if volume is not None and info is not None:
            return volume, info
        self.build_volume_from_frames(study_uid)
        volume, info = self._cache_get(study_uid)
        if volume is None or info is None:
            raise DicomVolumeError("Failed to build volume")
        return volume, info

    def render_mpr(
        self,
        study_uid: str,
        plane: str,
        slice_index: int,
        params: dict[str, Any] | None = None,
        *,
        max_edge: int | None = None,
    ) -> bytes:
        """Render an MPR slice as PNG."""
        if plane.lower() not in PLANES:
            raise DicomVolumeError(f"Invalid plane: {plane}")

        params = params or {}
        volume, info = self._get_volume_or_build(study_uid)
        spacing = tuple(info.get("spacing") or (1.0, 1.0, 1.0))
        slice_data = self._slice_volume(volume, plane, slice_index)
        slice_data = self._enhance_mpr_slice(slice_data, plane.lower(), volume.shape, spacing)
        rendered = self._normalize_for_display(slice_data, params, volume)
        return self._array_to_png(rendered, max_edge=max_edge)

    def render_volume(
        self, study_uid: str, params: dict[str, Any] | None = None, *, max_edge: int | None = None
    ) -> bytes:
        """Render a 3D projection (MIP or rotated MIP) as PNG."""
        params = params or {}
        volume, _info = self._get_volume_or_build(study_uid)
        mode = (params.get("mode") or "mip").lower()

        azimuth = float(params.get("azimuth", 0))
        elevation = float(params.get("elevation", 0))

        rotated = volume
        if azimuth or elevation:
            rotated = ndimage.rotate(volume, azimuth, axes=(1, 2), reshape=False, order=1)
            rotated = ndimage.rotate(rotated, elevation, axes=(0, 2), reshape=False, order=1)

        projection = self._project_volume(rotated, mode)

        rendered = self._normalize_for_display(projection, params, volume, is_projection=True)
        return self._array_to_png(rendered, max_edge=max_edge)

    def render_preview(
        self,
        study_uid: str,
        *,
        slices: dict[str, int] | None = None,
        params: dict[str, Any] | None = None,
        max_edge: int | None = None,
    ) -> dict[str, Any]:
        """Render VR + all MPR planes in one pass (single volume load)."""
        params = params or {}
        slices = slices or {}
        volume, info = self._get_volume_or_build(study_uid)
        z, y, x = volume.shape

        slice_idx = {
            "axial": int(slices.get("axial", z // 2)),
            "coronal": int(slices.get("coronal", y // 2)),
            "sagittal": int(slices.get("sagittal", x // 2)),
        }

        spacing = tuple(info.get("spacing") or (1.0, 1.0, 1.0))
        mpr_b64: dict[str, str] = {}
        for plane in ("axial", "coronal", "sagittal"):
            slice_data = self._slice_volume(volume, plane, slice_idx[plane])
            slice_data = self._enhance_mpr_slice(slice_data, plane, volume.shape, spacing)
            rendered = self._normalize_for_display(slice_data, params, volume)
            mpr_b64[plane] = base64.b64encode(self._array_to_png(rendered, max_edge=max_edge)).decode("ascii")

        mode = (params.get("mode") or "mip").lower()
        azimuth = float(params.get("azimuth", 0))
        elevation = float(params.get("elevation", 0))
        rotated = volume
        if azimuth or elevation:
            rotated = ndimage.rotate(volume, azimuth, axes=(1, 2), reshape=False, order=1)
            rotated = ndimage.rotate(rotated, elevation, axes=(0, 2), reshape=False, order=1)
        projection = self._project_volume(rotated, mode)
        vr_rendered = self._normalize_for_display(projection, params, volume, is_projection=True)
        vr_b64 = base64.b64encode(self._array_to_png(vr_rendered, max_edge=max_edge)).decode("ascii")

        study = self._get_study(study_uid)
        series = self._select_series(study) if study else None
        warning = self._volume_warning(series, num_slices=z)

        return {
            "study_uid": study_uid,
            "info": {**info, "cached": True, "status": "ready", "warning": warning},
            "slices": slice_idx,
            "render": vr_b64,
            "mpr": mpr_b64,
        }

    def invalidate_cache(self, study_uid: str) -> None:
        _mem_volume_cache.pop(study_uid, None)
        try:
            client = _redis_binary()
            client.delete(_volume_cache_key(study_uid, "data"))
            client.delete(_volume_cache_key(study_uid, "info"))
        except Exception:  # noqa: BLE001
            pass
        study = self._get_study(study_uid)
        if study:
            vdir = _disk_volume_dir(study.patient_id, study_uid)
            for name in ("volume.bin", "info.json"):
                p = vdir / name
                if p.exists():
                    p.unlink(missing_ok=True)


def enqueue_volume_prebuild(study_uid: str, *, num_slices: int = 0) -> None:
    """Warm volume cache after DICOM ingest (Celery or inline for small series)."""
    if not settings.DICOM_3D_ENABLED:
        return
    try:
        from app.tasks.celery_app import redis_available
        from app.tasks.dicom_volume_task import build_volume_from_study

        if num_slices and num_slices <= settings.DICOM_3D_SYNC_BUILD_MAX_SLICES:
            db = SessionLocal()
            try:
                DicomVolumeService(db).build_volume_from_frames(study_uid)
            finally:
                db.close()
            return

        if redis_available():
            build_volume_from_study.delay(study_uid)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Volume prebuild skipped for %s: %s", study_uid, exc)
