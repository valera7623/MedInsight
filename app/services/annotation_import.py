"""Import annotations from JSON / GeoJSON."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.services.dicom_annotations import AnnotationError, DicomAnnotationService

EXPORT_VERSION = "1.0"


class AnnotationImportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._ann_svc = DicomAnnotationService(db)

    def validate_json(self, json_data: str) -> bool:
        try:
            payload = json.loads(json_data)
        except json.JSONDecodeError:
            return False
        if isinstance(payload, list):
            return True
        if isinstance(payload, dict) and "annotations" in payload:
            return isinstance(payload["annotations"], list)
        return False

    def validate_geojson(self, geojson_data: str) -> bool:
        try:
            payload = json.loads(geojson_data)
        except json.JSONDecodeError:
            return False
        return isinstance(payload, dict) and payload.get("type") == "FeatureCollection"

    def import_from_json(
        self,
        frame_id: int,
        json_data: str,
        *,
        user_id: int,
        replace: bool = False,
    ) -> int:
        if not self.validate_json(json_data):
            raise AnnotationError("Invalid JSON format")
        payload = json.loads(json_data)
        items = payload.get("annotations") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise AnnotationError("Expected annotations array")

        if replace:
            self._ann_svc.batch_delete_annotations(frame_id)

        created = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            row = self._normalize_json_item(item, frame_id)
            self._ann_svc.create_annotation(row, user_id=user_id)
            created += 1
        return created

    def import_from_geojson(
        self,
        frame_id: int,
        geojson_data: str,
        *,
        user_id: int,
        replace: bool = False,
    ) -> int:
        if not self.validate_geojson(geojson_data):
            raise AnnotationError("Invalid GeoJSON FeatureCollection")
        payload = json.loads(geojson_data)
        features = payload.get("features") or []

        if replace:
            self._ann_svc.batch_delete_annotations(frame_id)

        created = 0
        for feat in features:
            if not isinstance(feat, dict):
                continue
            row = self._geojson_to_annotation(feat, frame_id)
            if row:
                self._ann_svc.create_annotation(row, user_id=user_id)
                created += 1
        return created

    def _normalize_json_item(self, item: dict[str, Any], frame_id: int) -> dict[str, Any]:
        measurement = item.get("measurement") or {}
        return {
            "frame_id": frame_id,
            "type": item.get("type", "rectangle"),
            "coordinates": item.get("coordinates") or {},
            "color": item.get("color", "#FF0000"),
            "label": item.get("label"),
            "measurement_value": measurement.get("value", item.get("measurement_value")),
            "measurement_unit": measurement.get("unit", item.get("measurement_unit")),
        }

    def _geojson_to_annotation(self, feat: dict[str, Any], frame_id: int) -> dict[str, Any] | None:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        ann_type = props.get("type", "line")
        coordinates: dict[str, Any] = {}

        if ann_type == "rectangle" and gtype == "Polygon" and coords:
            ring = coords[0]
            if len(ring) >= 2:
                coordinates = {"x1": ring[0][0], "y1": ring[0][1], "x2": ring[2][0], "y2": ring[2][1]}
        elif ann_type == "circle" and gtype == "Point" and coords:
            coordinates = {
                "cx": coords[0],
                "cy": coords[1],
                "radius": props.get("radius", 10),
            }
        elif gtype == "LineString" and coords and len(coords) >= 2:
            coordinates = {"x1": coords[0][0], "y1": coords[0][1], "x2": coords[1][0], "y2": coords[1][1]}
            if len(coords) >= 3:
                coordinates["x3"], coordinates["y3"] = coords[2][0], coords[2][1]
                ann_type = "angle"
        elif ann_type == "text" and gtype == "Point" and coords:
            coordinates = {"x": coords[0], "y": coords[1], "text": props.get("text", props.get("label", ""))}
        else:
            return None

        return {
            "frame_id": frame_id,
            "type": ann_type,
            "coordinates": coordinates,
            "color": props.get("color", "#FF0000"),
            "label": props.get("label"),
            "measurement_value": props.get("measurement_value"),
            "measurement_unit": props.get("measurement_unit"),
        }
