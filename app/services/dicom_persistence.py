"""DICOM DB helpers: duplicate handling, cleanup and idempotent writes."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import DicomFrame, DicomSeries, DicomStudy, Patient, User
from app.services.dicom_parser import DicomParseError
from app.services.dicom_storage import DicomStorage

logger = logging.getLogger(__name__)


def handle_cross_patient_conflict(
    db: Session,
    cross_patient: DicomStudy,
    current_user: User,
    storage: DicomStorage,
) -> None:
    """Resolve or reject upload when Study UID exists for another patient."""
    from fastapi import HTTPException, status

    from app.services.access import can_delete_dicom_study, can_view_patient, is_admin, is_super_admin

    conflict_patient = cross_patient.patient
    if conflict_patient is None:
        conflict_patient = db.query(Patient).filter(Patient.id == cross_patient.patient_id).first()

    can_view = conflict_patient is not None and can_view_patient(current_user, conflict_patient)

    if is_super_admin(current_user) or is_admin(current_user):
        delete_study_data(db, cross_patient, storage)
        db.commit()
        logger.info(
            "Admin replaced cross-patient DICOM conflict: study %s patient %s -> upload by user %s",
            cross_patient.study_uid,
            cross_patient.patient_id,
            current_user.id,
        )
        return

    if can_delete_dicom_study(current_user, cross_patient):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    f"Исследование уже загружено для пациента #{cross_patient.patient_id}. "
                    "Удалите существующую запись или выберите того же пациента."
                ),
                "conflict_patient_id": cross_patient.patient_id,
                "conflict_study_uid": cross_patient.study_uid,
                "conflict_visible": can_view,
                "can_delete": True,
            },
        )

    if can_view:
        message = (
            f"Исследование уже загружено для пациента #{cross_patient.patient_id}. "
            "У вас нет прав на удаление — обратитесь к администратору."
        )
    else:
        message = (
            f"Исследование с этим файлом уже есть у пациента #{cross_patient.patient_id}, "
            "но у вас нет доступа к этой записи. Обратитесь к администратору."
        )

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": message,
            "conflict_patient_id": cross_patient.patient_id,
            "conflict_study_uid": cross_patient.study_uid,
            "conflict_visible": can_view,
            "can_delete": False,
        },
    )


def cross_patient_conflict_message(
    db: Session,
    other: DicomStudy,
    study: DicomStudy,
    storage: DicomStorage,
) -> str | None:
    """Task-side cross-patient handling. Returns error text or None if admin replaced conflict."""
    from app.services.access import can_view_patient, is_admin, is_super_admin

    user = db.query(User).filter(User.id == study.user_id).first()
    if user and (is_super_admin(user) or is_admin(user)):
        delete_study_data(db, other, storage)
        db.flush()
        return None

    conflict_patient = db.query(Patient).filter(Patient.id == other.patient_id).first()
    if user and conflict_patient and can_view_patient(user, conflict_patient):
        return (
            f"Исследование уже загружено для пациента #{other.patient_id}. "
            "Удалите существующую запись или выберите того же пациента."
        )
    return (
        f"Исследование с этим файлом уже есть у пациента #{other.patient_id}, "
        "но у вас нет доступа к этой записи. Обратитесь к администратору."
    )


def read_study_uid_from_file(file_path: str) -> str | None:
    """Read StudyInstanceUID without loading pixel data."""
    try:
        import pydicom

        ds = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
        uid = getattr(ds, "StudyInstanceUID", None)
        return str(uid).strip() if uid else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Study UID read failed for %s: %s", file_path, exc)
        return None


def delete_study_data(db: Session, study: DicomStudy, storage: DicomStorage) -> None:
    """Remove on-disk assets and DB row (series/frames cascade via ORM)."""
    zip_path = study.zip_original_path
    study_uid = study.study_uid
    patient_id = study.patient_id

    if study.file_path_encrypted:
        try:
            Path(study.file_path_encrypted).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to delete encrypted DICOM %s: %s", study.file_path_encrypted, exc)

    if study_uid and not study_uid.startswith("pending-"):
        storage.delete_study(patient_id, study_uid)

    db.delete(study)
    db.flush()

    if zip_path:
        others = db.query(DicomStudy).filter(DicomStudy.zip_original_path == zip_path).count()
        if others == 0:
            try:
                Path(zip_path).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to delete ZIP archive %s: %s", zip_path, exc)


def clear_study_for_reprocess(db: Session, study: DicomStudy, storage: DicomStorage) -> None:
    """Drop series/frames and viewer files before re-processing an existing study row."""
    if study.study_uid.startswith("pending-"):
        return
    storage.delete_study(study.patient_id, study.study_uid)
    for series in list(study.series):
        db.delete(series)
    study.num_series = 0
    study.num_instances = 0
    study.file_path_encrypted = None
    db.flush()


def prepare_study_for_upload(
    db: Session,
    study: DicomStudy,
    parsed: dict,
    storage: DicomStorage,
) -> None:
    """Allow re-upload for the same patient; block cross-patient Study UID conflicts."""
    study_uid = parsed["study_uid"]
    series_uid = parsed["series_uid"]

    for other in (
        db.query(DicomStudy)
        .filter(DicomStudy.study_uid == study_uid, DicomStudy.id != study.id)
        .all()
    ):
        if other.patient_id != study.patient_id:
            msg = cross_patient_conflict_message(db, other, study, storage)
            if msg:
                raise DicomParseError(msg)
            continue
        if other.status == "processing":
            raise DicomParseError("Исследование уже обрабатывается. Подождите завершения.")
        delete_study_data(db, other, storage)

    other_series = (
        db.query(DicomSeries)
        .filter(DicomSeries.series_uid == series_uid, DicomSeries.study_id != study.id)
        .first()
    )
    if other_series:
        parent = db.query(DicomStudy).filter(DicomStudy.id == other_series.study_id).first()
        if not parent:
            db.delete(other_series)
            db.flush()
        elif parent.id == study.id:
            pass
        elif parent.patient_id != study.patient_id:
            raise DicomParseError(
                f"Серия DICOM уже привязана к пациенту #{parent.patient_id}. "
                "Удалите существующее исследование."
            )
        elif parent.status == "processing":
            raise DicomParseError("Исследование уже обрабатывается. Подождите завершения.")
        else:
            delete_study_data(db, parent, storage)

    clear_study_for_reprocess(db, study, storage)


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
            "Повторная загрузка для того же пациента заменит существующее исследование."
        )
    if "dicom_series.series_uid" in err:
        return (
            "Серия DICOM уже существует — повторите загрузку для того же пациента "
            "или удалите старое исследование."
        )
    if "dicom_frames.instance_uid" in err:
        return "Кадр DICOM уже существует. Удалите старое исследование и загрузите файл снова."
    return None
