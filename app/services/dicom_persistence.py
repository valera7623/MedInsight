"""DICOM DB helpers: duplicate detection and idempotent series/frame writes."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import DicomFrame, DicomSeries, DicomStudy
from app.services.dicom_parser import DicomParseError


def ensure_unique_dicom_ids(db: Session, study: DicomStudy, parsed: dict) -> None:
    """Reject upload when Study/Series UID already belongs to another study."""
    study_uid = parsed["study_uid"]
    series_uid = parsed["series_uid"]

    other_study = (
        db.query(DicomStudy)
        .filter(DicomStudy.study_uid == study_uid, DicomStudy.id != study.id)
        .first()
    )
    if other_study:
        raise DicomParseError(
            "Исследование с таким Study UID уже загружено. "
            "Удалите существующее исследование или загрузите другой файл."
        )

    other_series = (
        db.query(DicomSeries)
        .filter(DicomSeries.series_uid == series_uid, DicomSeries.study_id != study.id)
        .first()
    )
    if other_series:
        raise DicomParseError(
            "Серия DICOM уже существует — этот файл, вероятно, уже был загружен. "
            "Удалите существующее исследование и попробуйте снова."
        )


def get_or_create_series(db: Session, study: DicomStudy, parsed: dict) -> DicomSeries:
    """Return series for this study, reusing it on Celery retries."""
    series = (
        db.query(DicomSeries)
        .filter(DicomSeries.study_id == study.id, DicomSeries.series_uid == parsed["series_uid"])
        .first()
    )
    if series:
        for frame in list(series.frames):
            try:
                Path(frame.image_path).unlink(missing_ok=True)
            except OSError:
                pass
            db.delete(frame)
        db.flush()
        series.series_number = parsed.get("series_number")
        series.series_description = parsed.get("series_description")
        series.modality = parsed.get("modality")
        series.num_instances = 0
        return series

    series = DicomSeries(
        study_id=study.id,
        series_uid=parsed["series_uid"],
        series_number=parsed.get("series_number"),
        series_description=parsed.get("series_description"),
        modality=parsed.get("modality"),
        num_instances=0,
    )
    db.add(series)
    db.flush()
    return series


def add_frames_to_series(
    db: Session,
    series: DicomSeries,
    parsed_frames: list[dict],
    image_paths: list[str],
) -> None:
    for fmeta, img_path in zip(parsed_frames, image_paths, strict=True):
        db.add(
            DicomFrame(
                series_id=series.id,
                instance_uid=fmeta["instance_uid"],
                frame_number=fmeta["frame_number"],
                image_path=img_path,
                width=fmeta.get("width"),
                height=fmeta.get("height"),
                bit_depth=fmeta.get("bit_depth"),
                pixel_spacing=fmeta.get("pixel_spacing"),
            )
        )
    series.num_instances = len(parsed_frames)


def friendly_integrity_error(exc: Exception) -> str | None:
    err = str(getattr(exc, "orig", exc))
    if "dicom_studies.study_uid" in err:
        return (
            "Исследование с таким Study UID уже загружено. "
            "Удалите существующее исследование или загрузите другой файл."
        )
    if "dicom_series.series_uid" in err:
        return (
            "Серия DICOM уже существует — этот файл, вероятно, уже был загружен. "
            "Удалите существующее исследование и попробуйте снова."
        )
    if "dicom_frames.instance_uid" in err:
        return "Кадр DICOM уже существует. Удалите старое исследование и загрузите файл снова."
    return None
