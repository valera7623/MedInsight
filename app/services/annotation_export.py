"""Standardized annotation export: JSON, GeoJSON, PDF, batch ZIP."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import DicomAnnotation, DicomFrame, DicomSeries, DicomStudy, Patient, User
from app.services.dicom_annotations import AnnotationError, DicomAnnotationService

EXPORT_VERSION = "1.0"


class AnnotationExportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._ann_svc = DicomAnnotationService(db)

    def _load_frame(self, frame_id: int) -> DicomFrame:
        frame = (
            self.db.query(DicomFrame)
            .options(
                joinedload(DicomFrame.series)
                .joinedload(DicomSeries.study)
                .joinedload(DicomStudy.patient)
            )
            .filter(DicomFrame.id == frame_id)
            .first()
        )
        if not frame:
            raise AnnotationError("Frame not found")
        return frame

    def export_to_json(
        self,
        frame_id: int,
        *,
        user: User | None = None,
        anonymize: bool = False,
    ) -> str:
        frame = self._load_frame(frame_id)
        study = frame.series.study if frame.series else None
        series = frame.series
        patient = study.patient if study else None
        annotations = self._ann_svc.get_annotations(frame_id)

        payload: dict[str, Any] = {
            "version": EXPORT_VERSION,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "exported_by": None if anonymize else (user.full_name if user else None),
            "patient": self._patient_block(patient, anonymize),
            "study": self._study_block(study),
            "series": self._series_block(series),
            "frame": {
                "id": frame.id,
                "instance_uid": frame.instance_uid,
                "number": frame.frame_number,
                "width": frame.width,
                "height": frame.height,
                "pixel_spacing": frame.pixel_spacing,
            },
            "annotations": [self._annotation_export_item(a) for a in annotations],
            "metadata": {
                "total_annotations": len(annotations),
                "export_version": EXPORT_VERSION,
                "source": f"MedInsight v{settings.APP_VERSION}",
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def export_to_geojson(self, frame_id: int) -> str:
        annotations = self._ann_svc.get_annotations(frame_id)
        features = [self._to_geojson_feature(a) for a in annotations]
        return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)

    def export_to_pdf(self, frame_id: int, *, user: User | None = None, options: dict | None = None) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as pdf_canvas

        options = options or {}
        frame = self._load_frame(frame_id)
        study = frame.series.study if frame.series else None
        patient = study.patient if study else None
        annotations = self._ann_svc.get_annotations(frame_id)

        if not Path(frame.image_path).exists():
            raise AnnotationError("Frame image not found")

        buf = io.BytesIO()
        page_w, page_h = A4
        c = pdf_canvas.Canvas(buf, pagesize=A4)
        margin = 1.5 * cm
        y = page_h - margin

        # Header
        c.setFont("Helvetica-Bold", 14)
        title = study.study_description if study and study.study_description else "DICOM Annotations"
        c.drawString(margin, y, title[:80])
        y -= 0.6 * cm
        c.setFont("Helvetica", 10)
        if patient:
            pname = f"{patient.last_name} {patient.first_name}".strip()
            c.drawString(margin, y, f"Patient: {pname}")
            y -= 0.45 * cm
        if study and study.study_date:
            c.drawString(margin, y, f"Study date: {study.study_date.strftime('%Y-%m-%d')}")
            y -= 0.45 * cm
        c.drawString(margin, y, f"Frame: {frame.instance_uid[:40]}…")
        y -= 0.7 * cm

        # Image area
        img_max_w = page_w - 2 * margin - (5 * cm if annotations else 0)
        img_max_h = y - margin - 2 * cm
        iw, ih = frame.width or 512, frame.height or 512
        scale = min(img_max_w / iw, img_max_h / ih)
        draw_w, draw_h = iw * scale, ih * scale
        img_x, img_y = margin, y - draw_h

        try:
            from PIL import Image

            pil_img = Image.open(frame.image_path).convert("RGB")
            iw, ih = pil_img.size
            scale = min(img_max_w / iw, img_max_h / ih)
            draw_w, draw_h = iw * scale, ih * scale
            img_y = y - draw_h
            import io as _io

            buf_img = _io.BytesIO()
            pil_img.save(buf_img, format="PNG")
            buf_img.seek(0)
            c.drawImage(ImageReader(buf_img), img_x, img_y, width=draw_w, height=draw_h)
        except Exception:
            c.drawImage(ImageReader(frame.image_path), img_x, img_y, width=draw_w, height=draw_h)

        # Draw annotations (flip Y for PDF coords)
        for ann in annotations:
            self._draw_ann_on_pdf(c, ann, img_x, img_y, draw_w, draw_h, iw, ih)

        # Legend
        legend_x = page_w - margin - 4.5 * cm
        legend_y = page_h - margin - 1 * cm
        if annotations:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(legend_x, legend_y, "Legend")
            legend_y -= 0.5 * cm
            c.setFont("Helvetica", 8)
            for ann in annotations[:20]:
                c.setFillColor(self._hex_to_rl(ann.color))
                c.rect(legend_x, legend_y - 2, 8, 8, fill=1, stroke=0)
                c.setFillColor(colors.black)
                label = (ann.label or ann.type)[:24]
                c.drawString(legend_x + 12, legend_y, label)
                legend_y -= 0.4 * cm

        # Footer
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.grey)
        footer = f"Generated by MedInsight · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        if user:
            footer += f" · {user.full_name}"
        c.drawString(margin, 0.8 * cm, footer)

        c.showPage()
        c.save()
        return buf.getvalue()

    def export_batch(self, frame_ids: list[int], fmt: str, *, user: User | None = None) -> bytes:
        if len(frame_ids) > settings.DICOM_ANNOTATIONS_EXPORT_MAX_FRAMES:
            raise AnnotationError(
                f"Maximum {settings.DICOM_ANNOTATIONS_EXPORT_MAX_FRAMES} frames per batch export"
            )
        fmt = fmt.lower()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fid in frame_ids:
                if fmt == "json":
                    data = self.export_to_json(fid, user=user).encode("utf-8")
                    zf.writestr(f"frame_{fid}.json", data)
                elif fmt == "geojson":
                    data = self.export_to_geojson(fid).encode("utf-8")
                    zf.writestr(f"frame_{fid}.geojson", data)
                elif fmt == "pdf":
                    data = self.export_to_pdf(fid, user=user)
                    zf.writestr(f"frame_{fid}.pdf", data)
                else:
                    raise AnnotationError(f"Unsupported batch format: {fmt}")
        return buf.getvalue()

    @staticmethod
    def generate_legend_html(annotations: list[DicomAnnotation]) -> str:
        items = "".join(
            f'<li><span style="color:{a.color}">■</span> {(a.label or a.type)}</li>'
            for a in annotations
        )
        return f"<ul class='ann-legend'>{items}</ul>"

    def _annotation_export_item(self, ann: DicomAnnotation) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": ann.id,
            "type": ann.type,
            "coordinates": ann.coordinates,
            "color": ann.color,
            "label": ann.label,
            "created_at": ann.created_at.isoformat() if ann.created_at else None,
            "updated_at": ann.updated_at.isoformat() if ann.updated_at else None,
        }
        if ann.measurement_value is not None:
            item["measurement"] = {
                "value": ann.measurement_value,
                "unit": ann.measurement_unit or "mm",
            }
        return item

    def _to_geojson_feature(self, ann: DicomAnnotation) -> dict[str, Any]:
        coords = ann.coordinates or {}
        props: dict[str, Any] = {
            "id": ann.id,
            "type": ann.type,
            "label": ann.label,
            "color": ann.color,
            "measurement_value": ann.measurement_value,
            "measurement_unit": ann.measurement_unit,
            "created_at": ann.created_at.isoformat() if ann.created_at else None,
        }
        geometry: dict[str, Any]
        if ann.type == "rectangle":
            x1, y1 = coords.get("x1", 0), coords.get("y1", 0)
            x2, y2 = coords.get("x2", 0), coords.get("y2", 0)
            geometry = {
                "type": "Polygon",
                "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]],
            }
        elif ann.type == "circle":
            geometry = {
                "type": "Point",
                "coordinates": [coords.get("cx", 0), coords.get("cy", 0)],
            }
            props["radius"] = coords.get("radius", 0)
        elif ann.type in ("arrow", "line", "measurement", "angle"):
            pts = [[coords.get("x1", 0), coords.get("y1", 0)], [coords.get("x2", 0), coords.get("y2", 0)]]
            if ann.type == "angle" and "x3" in coords:
                pts.append([coords.get("x3", 0), coords.get("y3", 0)])
            geometry = {"type": "LineString", "coordinates": pts}
        elif ann.type == "text":
            geometry = {"type": "Point", "coordinates": [coords.get("x", 0), coords.get("y", 0)]}
            props["text"] = coords.get("text", ann.label)
        else:
            geometry = {"type": "GeometryCollection", "geometries": []}
        return {"type": "Feature", "geometry": geometry, "properties": props}

    def _draw_ann_on_pdf(self, c, ann, img_x, img_y, draw_w, draw_h, iw, ih) -> None:
        coords = ann.coordinates or {}
        sx, sy = draw_w / iw, draw_h / ih

        def tx(x: float) -> float:
            return img_x + x * sx

        def ty(y: float) -> float:
            return img_y + draw_h - y * sy

        c.setStrokeColor(self._hex_to_rl(ann.color))
        c.setFillColor(self._hex_to_rl(ann.color))
        if ann.type == "rectangle":
            x1, y1 = tx(min(coords.get("x1", 0), coords.get("x2", 0))), ty(max(coords.get("y1", 0), coords.get("y2", 0)))
            x2, y2 = tx(max(coords.get("x1", 0), coords.get("x2", 0))), ty(min(coords.get("y1", 0), coords.get("y2", 0)))
            c.rect(x1, y2, x2 - x1, y1 - y2, stroke=1, fill=0)
        elif ann.type == "circle":
            cx, cy = tx(coords.get("cx", 0)), ty(coords.get("cy", 0))
            r = (coords.get("radius", 0) or 0) * sx
            c.circle(cx, cy, r, stroke=1, fill=0)
        elif ann.type in ("line", "measurement", "arrow"):
            c.line(tx(coords.get("x1", 0)), ty(coords.get("y1", 0)), tx(coords.get("x2", 0)), ty(coords.get("y2", 0)))
        elif ann.type == "text":
            c.setFont("Helvetica", 10)
            c.drawString(tx(coords.get("x", 0)), ty(coords.get("y", 0)), coords.get("text") or ann.label or "")

    @staticmethod
    def _hex_to_rl(hex_color: str):
        from reportlab.lib import colors

        h = (hex_color or "#FF0000").lstrip("#")
        if len(h) == 6:
            return colors.HexColor(f"#{h}")
        return colors.red

    @staticmethod
    def _patient_block(patient: Patient | None, anonymize: bool) -> dict | None:
        if not patient:
            return None
        if anonymize:
            return {"id": None, "name": "ANONYMIZED", "birth_date": None}
        return {
            "id": patient.id,
            "name": f"{patient.last_name} {patient.first_name}".strip(),
            "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
        }

    @staticmethod
    def _study_block(study: DicomStudy | None) -> dict | None:
        if not study:
            return None
        return {
            "uid": study.study_uid,
            "date": study.study_date.isoformat() if study.study_date else None,
            "description": study.study_description,
            "modality": study.modality,
        }

    @staticmethod
    def _series_block(series: DicomSeries | None) -> dict | None:
        if not series:
            return None
        return {
            "uid": series.series_uid,
            "description": series.series_description,
            "modality": series.modality,
        }
