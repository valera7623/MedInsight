"""Extract structured text context from DICOM studies for GPT predictions."""

from __future__ import annotations

import json
import logging
import math
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import DicomAnnotation, DicomFrame, DicomSeries, DicomStudy, Document, Patient
from app.services.dicom_parser import DicomParser, _safe_str
from app.services.dicom_radiology_parser import DicomRadiologyParser
from app.services.dicom_measurement_extractor import DicomMeasurementExtractor
from app.services.encryption import decrypt_file

logger = logging.getLogger(__name__)

SR_MODALITIES = frozenset({"SR", "DOC", "OT"})

# Common DICOM tag names for extract_dicom_tags
TAG_ALIASES: dict[str, tuple[str, ...]] = {
    "PatientAge": ("PatientAge",),
    "PatientSex": ("PatientSex",),
    "SliceThickness": ("SliceThickness",),
    "SpacingBetweenSlices": ("SpacingBetweenSlices",),
    "ImagePositionPatient": ("ImagePositionPatient",),
    "PixelSpacing": ("PixelSpacing",),
    "StudyTime": ("StudyTime",),
    "AccessionNumber": ("AccessionNumber",),
    "InstitutionName": ("InstitutionName",),
}


class DicomTextExtractor:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._parser = DicomParser()
        self._radiology = DicomRadiologyParser(db)
        self._measurements = DicomMeasurementExtractor(db)

    def _get_study(self, study_uid: str) -> DicomStudy | None:
        return (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == study_uid)
            .first()
        )

    def _read_primary_dataset(self, study: DicomStudy) -> Any | None:
        if not study.file_path_encrypted:
            return None
        try:
            import pydicom

            raw = decrypt_file(study.file_path_encrypted)
            with tempfile.NamedTemporaryFile(suffix=".dcm", delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            try:
                return pydicom.dcmread(tmp_path, force=True)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cannot read encrypted DICOM for %s: %s", study.study_uid, exc)
            return None

    def extract_metadata(self, dicom_study_uid: str) -> dict[str, Any]:
        study = self._get_study(dicom_study_uid)
        if not study:
            raise ValueError("Study not found")

        series_desc = [s.series_description for s in study.series if s.series_description]
        ds = self._read_primary_dataset(study)
        extra: dict[str, Any] = {}
        if ds is not None:
            extra = self.extract_dicom_tags(
                dicom_study_uid,
                list(TAG_ALIASES.keys()),
                dataset=ds,
            )

        pixel_spacing = None
        for series in study.series:
            for frame in series.frames:
                if frame.pixel_spacing:
                    pixel_spacing = frame.pixel_spacing
                    break
            if pixel_spacing:
                break

        return {
            "study_uid": study.study_uid,
            "modality": study.modality,
            "body_part": study.body_part,
            "study_description": study.study_description,
            "series_descriptions": series_desc,
            "patient_name": study.patient_name_dicom,
            "patient_id_dicom": study.patient_id_dicom,
            "study_date": study.study_date.isoformat() if study.study_date else None,
            "num_series": study.num_series,
            "num_instances": study.num_instances,
            "pixel_spacing": pixel_spacing,
            **extra,
        }

    def extract_measurements(self, dicom_study_uid: str) -> list[dict[str, Any]]:
        study = self._get_study(dicom_study_uid)
        if not study:
            return []

        results: list[dict[str, Any]] = []
        frame_ids = [f.id for s in study.series for f in s.frames]
        if not frame_ids:
            return results

        annotations = (
            self.db.query(DicomAnnotation)
            .filter(DicomAnnotation.frame_id.in_(frame_ids), DicomAnnotation.deleted_at.is_(None))
            .all()
        )
        frame_by_id = {f.id: f for s in study.series for f in s.frames}

        for ann in annotations:
            frame = frame_by_id.get(ann.frame_id)
            spacing = (frame.pixel_spacing or {}) if frame else {}
            row_sp = float(spacing.get("row") or spacing.get("Row") or 1.0)
            col_sp = float(spacing.get("col") or spacing.get("Column") or 1.0)

            entry: dict[str, Any] = {
                "type": ann.type,
                "label": ann.label,
                "value": ann.measurement_value,
                "unit": ann.measurement_unit,
                "coordinates": ann.coordinates,
            }

            if ann.type in {"measurement", "line"} and ann.measurement_value is None:
                coords = ann.coordinates or {}
                x1, y1 = coords.get("x1"), coords.get("y1")
                x2, y2 = coords.get("x2"), coords.get("y2")
                if None not in (x1, y1, x2, y2):
                    px_dist = math.hypot(float(x2) - float(x1), float(y2) - float(y1))
                    mm = px_dist * ((row_sp + col_sp) / 2.0)
                    entry["value"] = round(mm, 2)
                    entry["unit"] = "mm"
                    entry["source"] = "annotation_geometry"

            if ann.type == "angle" and ann.measurement_value is not None:
                entry["unit"] = entry.get("unit") or "deg"

            if ann.type == "rectangle":
                coords = ann.coordinates or {}
                w_px = abs(float(coords.get("width", 0) or 0))
                h_px = abs(float(coords.get("height", 0) or 0))
                if w_px and h_px:
                    area_mm2 = w_px * row_sp * h_px * col_sp
                    entry["area_mm2"] = round(area_mm2, 2)

            results.append(entry)

        for series in study.series:
            for frame in series.frames:
                if frame.pixel_spacing:
                    results.append(
                        {
                            "type": "pixel_spacing",
                            "instance_uid": frame.instance_uid,
                            "value": frame.pixel_spacing,
                            "unit": "mm",
                            "source": "dicom_tag",
                        }
                    )

        return results

    def _walk_sr_content(self, dataset: Any, texts: list[str], depth: int = 0) -> None:
        if depth > 12:
            return
        if hasattr(dataset, "ContentSequence"):
            for item in dataset.ContentSequence:
                self._walk_sr_content(item, texts, depth + 1)
        for attr in ("TextValue", "ConceptNameCodeSequence"):
            if hasattr(dataset, attr) and attr == "TextValue":
                val = _safe_str(getattr(dataset, "TextValue", None), 4000)
                if val:
                    texts.append(val)

    def extract_structured_report(self, dicom_study_uid: str) -> str:
        study = self._get_study(dicom_study_uid)
        if not study:
            return ""

        texts: list[str] = []
        for series in study.series:
            if (series.modality or "").upper() in SR_MODALITIES:
                if series.series_description:
                    texts.append(series.series_description)

        ds = self._read_primary_dataset(study)
        if ds is not None:
            if (getattr(ds, "Modality", "") or "").upper() in SR_MODALITIES:
                self._walk_sr_content(ds, texts)
            for elem in getattr(ds, "ContentSequence", []) or []:
                self._walk_sr_content(elem, texts)

        return "\n".join(dict.fromkeys(texts))

    def extract_dicom_tags(
        self,
        dicom_study_uid: str,
        tags: list[str],
        *,
        dataset: Any | None = None,
    ) -> dict[str, Any]:
        study = self._get_study(dicom_study_uid)
        if not study and dataset is None:
            return {}

        ds = dataset or self._read_primary_dataset(study)  # type: ignore[arg-type]
        if ds is None:
            return {}

        out: dict[str, Any] = {}
        for tag in tags:
            if hasattr(ds, tag):
                val = getattr(ds, tag)
                if hasattr(val, "tolist"):
                    val = val.tolist()
                elif isinstance(val, (list, tuple)):
                    val = [float(x) for x in val] if tag in {"PixelSpacing", "ImagePositionPatient"} else list(val)
                out[tag] = val
        return out

    def _lab_results_from_documents(self, patient_id: int) -> dict[str, Any]:
        docs = (
            self.db.query(Document)
            .filter(Document.patient_id == patient_id)
            .all()
        )
        labs: dict[str, Any] = {}
        for doc in docs:
            if not doc.parsed_data:
                continue
            doc_labs = doc.parsed_data.get("lab_results") or doc.parsed_data.get("labs") or {}
            if isinstance(doc_labs, dict):
                labs.update(doc_labs)
        return labs

    def build_clinical_context(self, dicom_study_uid: str, patient_id: int) -> str:
        study = self._get_study(dicom_study_uid)
        if not study:
            raise ValueError("Study not found")

        patient = self.db.query(Patient).filter(Patient.id == patient_id).first()
        metadata = self.extract_metadata(dicom_study_uid)
        measurements_raw = self.extract_measurements(dicom_study_uid)
        sr_text = self.extract_structured_report(dicom_study_uid)

        meas_bundle = self._measurements.extract_all(dicom_study_uid)
        report = self._radiology.parse_radiology_report(dicom_study_uid, sr_text=sr_text)

        age = None
        if patient and patient.birth_date:
            today = datetime.utcnow().date()
            age = today.year - patient.birth_date.year

        context = {
            "patient": {
                "name": metadata.get("patient_name") or (
                    f"{patient.last_name} {patient.first_name}" if patient else None
                ),
                "age": age,
                "sex": metadata.get("PatientSex"),
                "patient_id": patient_id,
            },
            "study": {
                "modality": metadata.get("modality"),
                "body_part": metadata.get("body_part"),
                "description": metadata.get("study_description"),
                "date": metadata.get("study_date"),
                "series_descriptions": metadata.get("series_descriptions", []),
            },
            "findings": report.get("findings", []),
            "impression": report.get("impression", ""),
            "recommendations": report.get("recommendations", []),
            "measurements": {
                "annotations": measurements_raw,
                "organs": meas_bundle.get("organs", {}),
                "tumors": meas_bundle.get("tumors", []),
                "bones": meas_bundle.get("bones", []),
                "vessels": meas_bundle.get("vessels", []),
            },
            "structured_report_excerpt": sr_text[:2000] if sr_text else "",
            "lab_results": self._lab_results_from_documents(patient_id),
            "dicom_tags": {
                k: metadata.get(k)
                for k in ("SliceThickness", "SpacingBetweenSlices", "PixelSpacing", "ImagePositionPatient")
                if metadata.get(k) is not None
            },
        }
        return json.dumps(context, ensure_ascii=False, indent=2)

    def process_study(self, dicom_study_uid: str) -> DicomStudy:
        """Full extraction pipeline; persists results on DicomStudy."""
        study = self._get_study(dicom_study_uid)
        if not study:
            raise ValueError("Study not found")

        sr_text = self.extract_structured_report(dicom_study_uid)
        report = self._radiology.parse_radiology_report(dicom_study_uid, sr_text=sr_text)
        meas_bundle = self._measurements.extract_all(dicom_study_uid)
        clinical_text = self.build_clinical_context(dicom_study_uid, study.patient_id)

        study.radiology_findings = report.get("findings", [])
        study.radiology_impression = report.get("impression") or None
        study.extracted_measurements = meas_bundle
        study.clinical_context = clinical_text
        study.clinical_context_processed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(study)
        return study
