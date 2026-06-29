"""DICOM viewer helpers — study/series/frame URLs and metadata."""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models import DicomFrame, DicomSeries, DicomStudy
from app.services.dicom_storage import DicomStorage


class DicomViewer:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.storage = DicomStorage()

    def get_study(self, study_uid: str) -> DicomStudy | None:
        return (
            self.db.query(DicomStudy)
            .options(joinedload(DicomStudy.series).joinedload(DicomSeries.frames))
            .filter(DicomStudy.study_uid == study_uid)
            .first()
        )

    def get_study_info(self, study_uid: str) -> dict | None:
        study = self.get_study(study_uid)
        if not study:
            return None
        return {
            "id": study.id,
            "study_uid": study.study_uid,
            "patient_id": study.patient_id,
            "tenant_id": study.tenant_id,
            "study_date": study.study_date.isoformat() if study.study_date else None,
            "study_description": study.study_description,
            "modality": study.modality,
            "body_part": study.body_part,
            "patient_name_dicom": study.patient_name_dicom,
            "patient_id_dicom": study.patient_id_dicom,
            "num_series": study.num_series,
            "num_instances": study.num_instances,
            "status": study.status,
            "created_at": study.created_at.isoformat() if study.created_at else None,
            "processed_at": study.processed_at.isoformat() if study.processed_at else None,
            "series": [
                {
                    "series_uid": s.series_uid,
                    "series_number": s.series_number,
                    "series_description": s.series_description,
                    "modality": s.modality,
                    "num_instances": s.num_instances,
                    "frames": [
                        {
                            "id": f.id,
                            "instance_uid": f.instance_uid,
                            "frame_number": f.frame_number,
                            "image_url": self.get_frame_url(study.study_uid, f.instance_uid, f.frame_number),
                            "width": f.width,
                            "height": f.height,
                            "pixel_spacing": f.pixel_spacing,
                            "annotate_url": (
                                f"/dicom/annotate/{study.study_uid}/{s.series_uid}/{f.instance_uid}"
                            ),
                        }
                        for f in sorted(s.frames, key=lambda x: x.frame_number)
                    ],
                }
                for s in sorted(study.series, key=lambda x: x.series_number or 0)
            ],
        }

    def get_series_info(self, series_uid: str) -> dict | None:
        series = (
            self.db.query(DicomSeries)
            .options(joinedload(DicomSeries.frames), joinedload(DicomSeries.study))
            .filter(DicomSeries.series_uid == series_uid)
            .first()
        )
        if not series or not series.study:
            return None
        study = series.study
        return {
            "series_uid": series.series_uid,
            "study_uid": study.study_uid,
            "series_number": series.series_number,
            "series_description": series.series_description,
            "modality": series.modality,
            "frames": [
                {
                    "id": f.id,
                    "instance_uid": f.instance_uid,
                    "frame_number": f.frame_number,
                    "image_url": self.get_frame_url(study.study_uid, f.instance_uid, f.frame_number),
                    "width": f.width,
                    "height": f.height,
                    "pixel_spacing": f.pixel_spacing,
                    "annotate_url": (
                        f"/dicom/annotate/{study.study_uid}/{series.series_uid}/{f.instance_uid}"
                    ),
                }
                for f in sorted(series.frames, key=lambda x: x.frame_number)
            ],
        }

    def get_frame_url(self, study_uid: str, instance_uid: str, frame_index: int = 0) -> str:
        return f"/api/dicom/frames/{instance_uid}?study_uid={study_uid}&frame={frame_index}"

    def get_thumbnail(self, study_uid: str) -> str | None:
        study = self.get_study(study_uid)
        if not study or not study.series:
            return None
        for series in sorted(study.series, key=lambda s: s.series_number or 0):
            if series.frames:
                frame = sorted(series.frames, key=lambda f: f.frame_number)[0]
                return self.get_frame_url(study_uid, frame.instance_uid, frame.frame_number)
        return None

    def resolve_frame(self, instance_uid: str, *, study_uid: str | None = None) -> DicomFrame | None:
        query = self.db.query(DicomFrame).filter(DicomFrame.instance_uid == instance_uid)
        frame = query.first()
        if frame:
            return frame
        if study_uid:
            study = self.get_study(study_uid)
            if study:
                for series in study.series:
                    for f in series.frames:
                        if f.instance_uid == instance_uid or f.instance_uid.startswith(instance_uid):
                            return f
        return None
