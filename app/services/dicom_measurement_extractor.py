"""Extract organ/tumor/bone/vessel measurements from DICOM annotations."""

from __future__ import annotations

import math
import re
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import DicomAnnotation, DicomSeries, DicomStudy

TUMOR_KEYWORDS = re.compile(
    r"опухол|tumor|mass|lesion|узел|ноду|metasta|неоплаз",
    re.IGNORECASE,
)
BONE_KEYWORDS = re.compile(
    r"перелом|fracture|кост|bone|disloc|вывих|смещ",
    re.IGNORECASE,
)
VESSEL_KEYWORDS = re.compile(
    r"сосуд|vessel|arter|вен|stenos|стеноз|кальциф|aneurysm|аневризм",
    re.IGNORECASE,
)
ORGAN_KEYWORDS = re.compile(
    r"печен|liver|селез|kidney|почк|лёгк|lung|сердц|heart|ventric",
    re.IGNORECASE,
)


class DicomMeasurementExtractor:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _study_annotations(self, study_uid: str) -> list[tuple[DicomAnnotation, DicomStudy]]:
        study = (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == study_uid)
            .first()
        )
        if not study:
            return []

        frame_map = {f.id: f for s in study.series for f in s.frames}
        frame_ids = list(frame_map.keys())
        if not frame_ids:
            return []

        anns = (
            self.db.query(DicomAnnotation)
            .filter(DicomAnnotation.frame_id.in_(frame_ids), DicomAnnotation.deleted_at.is_(None))
            .all()
        )
        return [(a, study) for a in anns]

    def _mm_from_annotation(self, ann: DicomAnnotation, frame) -> float | None:
        if ann.measurement_value is not None:
            return float(ann.measurement_value)
        coords = ann.coordinates or {}
        spacing = frame.pixel_spacing or {}
        row_sp = float(spacing.get("row") or 1.0)
        col_sp = float(spacing.get("col") or 1.0)
        if ann.type in {"measurement", "line"}:
            x1, y1, x2, y2 = coords.get("x1"), coords.get("y1"), coords.get("x2"), coords.get("y2")
            if None not in (x1, y1, x2, y2):
                px = math.hypot(float(x2) - float(x1), float(y2) - float(y1))
                return round(px * ((row_sp + col_sp) / 2.0), 2)
        if ann.type == "rectangle":
            w = abs(float(coords.get("width", 0) or 0))
            h = abs(float(coords.get("height", 0) or 0))
            if w and h:
                return round(max(w * col_sp, h * row_sp), 2)
        return None

    def _volume_cc(self, ann: DicomAnnotation, frame) -> float | None:
        coords = ann.coordinates or {}
        spacing = frame.pixel_spacing or {}
        row_sp = float(spacing.get("row") or 1.0)
        col_sp = float(spacing.get("col") or 1.0)
        w = abs(float(coords.get("width", 0) or 0))
        h = abs(float(coords.get("height", 0) or 0))
        if not w or not h:
            return None
        depth_mm = ann.measurement_value or min(w, h)
        vol_mm3 = w * col_sp * h * row_sp * float(depth_mm)
        return round(vol_mm3 / 1000.0, 2)

    def extract_organ_sizes(self, dicom_study_uid: str) -> dict[str, Any]:
        organs: dict[str, Any] = {}
        study = (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == dicom_study_uid)
            .first()
        )
        if not study:
            return organs

        frame_map = {f.id: f for s in study.series for f in s.frames}
        for ann, _ in self._study_annotations(dicom_study_uid):
            label = ann.label or ""
            if not ORGAN_KEYWORDS.search(label):
                continue
            frame = frame_map.get(ann.frame_id)
            size_mm = self._mm_from_annotation(ann, frame) if frame else None
            key = label.strip() or f"organ_{ann.id}"
            organs[key] = {
                "size_mm": size_mm,
                "unit": ann.measurement_unit or "mm",
                "annotation_type": ann.type,
            }
        return organs

    def extract_tumor_measurements(self, dicom_study_uid: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        frame_map = {}
        study = (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == dicom_study_uid)
            .first()
        )
        if study:
            frame_map = {f.id: f for s in study.series for f in s.frames}

        for ann, _ in self._study_annotations(dicom_study_uid):
            label = ann.label or ""
            if not TUMOR_KEYWORDS.search(label) and ann.type not in {"rectangle", "circle"}:
                continue
            if ann.type in {"rectangle", "circle"} and not TUMOR_KEYWORDS.search(label):
                continue
            frame = frame_map.get(ann.frame_id)
            entry = {
                "label": label or "lesion",
                "size_mm": self._mm_from_annotation(ann, frame) if frame else ann.measurement_value,
                "volume_cc": self._volume_cc(ann, frame) if frame else None,
                "density_hu": None,
                "annotation_id": ann.id,
            }
            results.append(entry)
        return results

    def extract_bone_measurements(self, dicom_study_uid: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        frame_map = {}
        study = (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == dicom_study_uid)
            .first()
        )
        if study:
            frame_map = {f.id: f for s in study.series for f in s.frames}

        for ann, _ in self._study_annotations(dicom_study_uid):
            label = ann.label or ""
            if not BONE_KEYWORDS.search(label) and ann.type != "angle":
                continue
            frame = frame_map.get(ann.frame_id)
            results.append(
                {
                    "label": label or "bone",
                    "length_mm": self._mm_from_annotation(ann, frame) if frame else ann.measurement_value,
                    "angle_deg": ann.measurement_value if ann.type == "angle" else None,
                    "displacement_mm": ann.measurement_value if "смещ" in label.lower() else None,
                    "annotation_id": ann.id,
                }
            )
        return results

    def extract_vessel_measurements(self, dicom_study_uid: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        frame_map = {}
        study = (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == dicom_study_uid)
            .first()
        )
        if study:
            frame_map = {f.id: f for s in study.series for f in s.frames}

        for ann, _ in self._study_annotations(dicom_study_uid):
            label = ann.label or ""
            if not VESSEL_KEYWORDS.search(label):
                continue
            frame = frame_map.get(ann.frame_id)
            diameter = self._mm_from_annotation(ann, frame) if frame else ann.measurement_value
            stenosis = None
            if ann.measurement_value and "%" in (ann.measurement_unit or ""):
                stenosis = ann.measurement_value
            results.append(
                {
                    "label": label,
                    "diameter_mm": diameter,
                    "stenosis_percent": stenosis,
                    "calcification": "кальциф" in label.lower(),
                    "annotation_id": ann.id,
                }
            )
        return results

    def extract_all(self, dicom_study_uid: str) -> dict[str, Any]:
        return {
            "organs": self.extract_organ_sizes(dicom_study_uid),
            "tumors": self.extract_tumor_measurements(dicom_study_uid),
            "bones": self.extract_bone_measurements(dicom_study_uid),
            "vessels": self.extract_vessel_measurements(dicom_study_uid),
        }
