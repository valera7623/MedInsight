"""DICOM frame annotation CRUD, export and session tracking."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import DicomAnnotation, DicomAnnotationSession, DicomFrame, DicomSeries, DicomStudy

logger = logging.getLogger(__name__)

ANNOTATION_TYPES = frozenset(
    {"rectangle", "circle", "arrow", "text", "line", "measurement", "angle"}
)


class AnnotationError(Exception):
    pass


class DicomAnnotationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _active_query(self):
        return self.db.query(DicomAnnotation).filter(DicomAnnotation.deleted_at.is_(None))

    def _count_frame_annotations(self, frame_id: int) -> int:
        return self._active_query().filter(DicomAnnotation.frame_id == frame_id).count()

    def _validate_type(self, ann_type: str) -> str:
        t = (ann_type or "").strip().lower()
        if t not in ANNOTATION_TYPES:
            raise AnnotationError(f"Unsupported annotation type: {ann_type}")
        return t

    def create_annotation(self, data: dict, *, user_id: int) -> DicomAnnotation:
        if not settings.DICOM_ANNOTATIONS_ENABLED:
            raise AnnotationError("DICOM annotations are disabled")

        frame_id = int(data["frame_id"])
        if self._count_frame_annotations(frame_id) >= settings.DICOM_ANNOTATIONS_MAX_PER_FRAME:
            raise AnnotationError(
                f"Maximum {settings.DICOM_ANNOTATIONS_MAX_PER_FRAME} annotations per frame"
            )

        ann = DicomAnnotation(
            frame_id=frame_id,
            user_id=user_id,
            type=self._validate_type(data["type"]),
            coordinates=dict(data.get("coordinates") or {}),
            color=str(data.get("color") or "#FF0000")[:16],
            label=(str(data["label"]).strip()[:255] if data.get("label") else None),
            measurement_value=float(data["measurement_value"]) if data.get("measurement_value") is not None else None,
            measurement_unit=(str(data["measurement_unit"])[:16] if data.get("measurement_unit") else None),
        )
        self.db.add(ann)
        self.db.commit()
        self.db.refresh(ann)
        return ann

    def get_annotations(self, frame_id: int) -> list[DicomAnnotation]:
        return (
            self._active_query()
            .filter(DicomAnnotation.frame_id == frame_id)
            .order_by(DicomAnnotation.id)
            .all()
        )

    def get_annotations_for_frame(self, frame_instance_uid: str) -> list[DicomAnnotation]:
        frame = (
            self.db.query(DicomFrame)
            .filter(DicomFrame.instance_uid == frame_instance_uid)
            .first()
        )
        if not frame:
            return []
        return self.get_annotations(frame.id)

    def get_annotation(self, annotation_id: int) -> DicomAnnotation | None:
        return self._active_query().filter(DicomAnnotation.id == annotation_id).first()

    def update_annotation(self, annotation_id: int, data: dict, *, user_id: int) -> DicomAnnotation:
        ann = self.get_annotation(annotation_id)
        if not ann:
            raise AnnotationError("Annotation not found")
        if ann.user_id != user_id:
            raise AnnotationError("Cannot modify another user's annotation")

        if "type" in data and data["type"]:
            ann.type = self._validate_type(data["type"])
        if "coordinates" in data and data["coordinates"] is not None:
            ann.coordinates = dict(data["coordinates"])
        if "color" in data and data["color"]:
            ann.color = str(data["color"])[:16]
        if "label" in data:
            ann.label = str(data["label"]).strip()[:255] if data["label"] else None
        if "measurement_value" in data:
            ann.measurement_value = (
                float(data["measurement_value"]) if data["measurement_value"] is not None else None
            )
        if "measurement_unit" in data:
            ann.measurement_unit = (
                str(data["measurement_unit"])[:16] if data["measurement_unit"] else None
            )
        ann.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ann)
        return ann

    def delete_annotation(self, annotation_id: int, *, user_id: int) -> bool:
        ann = self.get_annotation(annotation_id)
        if not ann:
            return False
        if ann.user_id != user_id:
            raise AnnotationError("Cannot delete another user's annotation")
        ann.deleted_at = datetime.utcnow()
        self.db.commit()
        return True

    def batch_delete_annotations(self, frame_id: int, *, user_id: int | None = None) -> int:
        query = self._active_query().filter(DicomAnnotation.frame_id == frame_id)
        if user_id is not None:
            query = query.filter(DicomAnnotation.user_id == user_id)
        rows = query.all()
        now = datetime.utcnow()
        for ann in rows:
            ann.deleted_at = now
        self.db.commit()
        return len(rows)

    def export_annotations_to_json(self, frame_id: int, *, anonymize: bool = False) -> str:
        items = [self._serialize(ann, anonymize=anonymize) for ann in self.get_annotations(frame_id)]
        return json.dumps({"frame_id": frame_id, "annotations": items}, ensure_ascii=False, indent=2)

    def import_annotations_from_json(
        self,
        frame_id: int,
        json_data: str,
        *,
        user_id: int,
        replace: bool = False,
    ) -> int:
        payload = json.loads(json_data)
        items = payload.get("annotations") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise AnnotationError("Invalid JSON: expected annotations array")

        if replace:
            self.batch_delete_annotations(frame_id)

        created = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item["frame_id"] = frame_id
            self.create_annotation(item, user_id=user_id)
            created += 1
        return created

    def export_annotations_to_geojson(self, frame_id: int) -> str:
        features: list[dict[str, Any]] = []
        for ann in self.get_annotations(frame_id):
            coords = ann.coordinates or {}
            geometry: dict[str, Any]
            if ann.type == "circle":
                geometry = {
                    "type": "Point",
                    "coordinates": [coords.get("cx", 0), coords.get("cy", 0)],
                }
            elif ann.type in ("rectangle", "line", "arrow", "measurement"):
                geometry = {
                    "type": "LineString",
                    "coordinates": [
                        [coords.get("x1", 0), coords.get("y1", 0)],
                        [coords.get("x2", 0), coords.get("y2", 0)],
                    ],
                }
            elif ann.type == "text":
                geometry = {
                    "type": "Point",
                    "coordinates": [coords.get("x", 0), coords.get("y", 0)],
                }
            else:
                geometry = {"type": "GeometryCollection", "geometries": []}

            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "id": ann.id,
                        "type": ann.type,
                        "color": ann.color,
                        "label": ann.label,
                        "measurement_value": ann.measurement_value,
                        "measurement_unit": ann.measurement_unit,
                    },
                }
            )
        return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)

    def clone_annotations_to_frame(self, source_frame_id: int, target_frame_id: int, *, user_id: int) -> int:
        source = self.get_annotations(source_frame_id)
        count = 0
        for ann in source:
            self.create_annotation(
                {
                    "frame_id": target_frame_id,
                    "type": ann.type,
                    "coordinates": ann.coordinates,
                    "color": ann.color,
                    "label": ann.label,
                    "measurement_value": ann.measurement_value,
                    "measurement_unit": ann.measurement_unit,
                },
                user_id=user_id,
            )
            count += 1
        return count

    def start_session(
        self,
        *,
        user_id: int,
        study_uid: str,
        series_uid: str,
        frame_instance_uid: str,
    ) -> DicomAnnotationSession:
        open_sessions = (
            self.db.query(DicomAnnotationSession)
            .filter(
                DicomAnnotationSession.user_id == user_id,
                DicomAnnotationSession.closed_at.is_(None),
            )
            .all()
        )
        now = datetime.utcnow()
        for sess in open_sessions:
            sess.closed_at = now

        session = DicomAnnotationSession(
            user_id=user_id,
            study_uid=study_uid,
            series_uid=series_uid,
            frame_instance_uid=frame_instance_uid,
            opened_at=now,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_annotation_session(self, user_id: int, study_uid: str | None = None) -> DicomAnnotationSession | None:
        query = (
            self.db.query(DicomAnnotationSession)
            .filter(DicomAnnotationSession.user_id == user_id)
            .order_by(DicomAnnotationSession.opened_at.desc())
        )
        if study_uid:
            query = query.filter(DicomAnnotationSession.study_uid == study_uid)
        return query.first()

    def close_session(self, user_id: int, session_id: int | None = None) -> bool:
        query = self.db.query(DicomAnnotationSession).filter(
            DicomAnnotationSession.user_id == user_id,
            DicomAnnotationSession.closed_at.is_(None),
        )
        if session_id is not None:
            query = query.filter(DicomAnnotationSession.id == session_id)
        sessions = query.all()
        if not sessions:
            return False
        now = datetime.utcnow()
        for sess in sessions:
            sess.closed_at = now
        self.db.commit()
        return True

    def export_annotations_to_pdf(self, frame_id: int, output_path: str | Path) -> Path:
        """Render frame image with annotation overlays to PDF (reportlab)."""
        from reportlab.lib.pagesizes import landscape
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as pdf_canvas

        frame = (
            self.db.query(DicomFrame)
            .options(joinedload(DicomFrame.series).joinedload(DicomSeries.study))
            .filter(DicomFrame.id == frame_id)
            .first()
        )
        if not frame or not Path(frame.image_path).exists():
            raise AnnotationError("Frame image not found")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        img_path = frame.image_path
        c = pdf_canvas.Canvas(str(out), pagesize=landscape((frame.width or 800, frame.height or 600)))
        w, h = frame.width or 800, frame.height or 600
        c.drawImage(ImageReader(img_path), 0, 0, width=w, height=h)

        for ann in self.get_annotations(frame_id):
            coords = ann.coordinates or {}
            c.setStrokeColor(ann.color)
            c.setFillColor(ann.color)
            if ann.type == "rectangle":
                x1, y1 = coords.get("x1", 0), h - coords.get("y1", 0)
                x2, y2 = coords.get("x2", 0), h - coords.get("y2", 0)
                c.rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1), stroke=1, fill=0)
            elif ann.type == "line" or ann.type == "measurement":
                c.line(
                    coords.get("x1", 0),
                    h - coords.get("y1", 0),
                    coords.get("x2", 0),
                    h - coords.get("y2", 0),
                )
            if ann.label:
                c.drawString(coords.get("x1", 0), h - coords.get("y1", 0), ann.label)

        c.showPage()
        c.save()
        return out

    @staticmethod
    def _serialize(ann: DicomAnnotation, *, anonymize: bool = False) -> dict[str, Any]:
        return {
            "id": ann.id,
            "frame_id": ann.frame_id,
            "user_id": None if anonymize else ann.user_id,
            "type": ann.type,
            "coordinates": ann.coordinates,
            "color": ann.color,
            "label": ann.label,
            "measurement_value": ann.measurement_value,
            "measurement_unit": ann.measurement_unit,
            "created_at": ann.created_at.isoformat() if ann.created_at else None,
            "updated_at": ann.updated_at.isoformat() if ann.updated_at else None,
        }


def get_frame_with_study(db: Session, frame_id: int) -> DicomFrame | None:
    return (
        db.query(DicomFrame)
        .options(joinedload(DicomFrame.series).joinedload(DicomSeries.study).joinedload(DicomStudy.patient))
        .filter(DicomFrame.id == frame_id)
        .first()
    )


def get_frame_by_instance_uid(db: Session, instance_uid: str) -> DicomFrame | None:
    return (
        db.query(DicomFrame)
        .options(joinedload(DicomFrame.series).joinedload(DicomSeries.study).joinedload(DicomStudy.patient))
        .filter(DicomFrame.instance_uid == instance_uid)
        .first()
    )
