"""Celery task: parse DICOM upload and persist study/series/frames."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import DicomStudy, Patient
from app.services.dicom_parser import DicomParser, DicomParseError
from app.services.dicom_persistence import (
    add_frames_to_series,
    friendly_integrity_error,
    get_or_create_series,
    prepare_study_for_upload,
)
from app.services.dicom_storage import DicomStorage
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _notify_dicom_ready(study: DicomStudy, user_id: int) -> None:
    try:
        from app.websocket.events import EVENT_DICOM_READY, publish_event

        publish_event(
            EVENT_DICOM_READY,
            {
                "study_uid": study.study_uid,
                "patient_id": study.patient_id,
                "modality": study.modality,
                "status": study.status,
            },
            user_id=user_id,
            tenant_id=study.tenant_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("WS dicom.ready failed: %s", exc)

    try:
        from app.config import settings

        if not settings.TELEGRAM_BOT_ENABLED:
            return
        from app.bot.services.notification_service import get_notification_service

        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.id == study.patient_id).first()
            name = f"{patient.last_name} {patient.first_name}".strip() if patient else "пациент"
        finally:
            db.close()
        msg = (
            f"🩻 <b>DICOM исследование готово</b>\n"
            f"Пациент: {name}\n"
            f"Модальность: {study.modality or '—'}\n"
            f"Кадров: {study.num_instances}"
        )
        get_notification_service().send_bulk_notification([user_id], msg)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Telegram dicom notification failed: %s", exc)


def _mark_study_failed(db, study_id: int, message: str) -> None:
    study = db.query(DicomStudy).filter(DicomStudy.id == study_id).first()
    if not study:
        return
    study.status = "failed"
    study.error_message = message
    study.processed_at = datetime.utcnow()
    db.commit()


@celery_app.task(bind=True, name="app.tasks.dicom_task.process_dicom_study")
def process_dicom_study(self, study_id: int, temp_path: str) -> dict:
    db = SessionLocal()
    parser = DicomParser()
    storage = DicomStorage()
    study = None
    try:
        study = db.query(DicomStudy).filter(DicomStudy.id == study_id).first()
        if not study:
            return {"status": "failed", "error": "Study not found"}

        if study.status == "ready" and not study.study_uid.startswith("pending-"):
            # Re-upload sets status to processing before enqueue; ready here means skip duplicate task.
            return {
                "status": "ready",
                "study_uid": study.study_uid,
                "num_instances": study.num_instances,
            }

        study.status = "processing"
        db.commit()

        parsed = parser.parse_dicom_file(temp_path)
        prepare_study_for_upload(db, study, parsed, storage)

        frame_tuples = [(f["instance_uid"], f["frame_number"], f["png_bytes"]) for f in parsed["frames"]]
        image_paths = storage.store_frames(
            patient_id=study.patient_id,
            study_uid=parsed["study_uid"],
            frames=frame_tuples,
        )

        series = get_or_create_series(db, study, parsed)
        add_frames_to_series(db, series, parsed["frames"], image_paths)

        study.study_uid = parsed["study_uid"]
        study.study_date = parsed.get("study_date") or study.study_date
        study.study_description = parsed.get("study_description")
        study.modality = parsed.get("modality")
        study.body_part = parsed.get("body_part")
        study.patient_name_dicom = parsed.get("patient_name")
        study.patient_id_dicom = parsed.get("patient_id")
        study.num_series = 1
        study.num_instances = len(parsed["frames"])
        study.status = "ready"
        study.processed_at = datetime.utcnow()
        study.error_message = None
        db.commit()

        try:
            enc_path = storage.store_encrypted(
                temp_path,
                tenant_id=study.tenant_id,
                patient_id=study.patient_id,
                study_uid=parsed["study_uid"],
                filename=study.original_filename or "upload.dcm",
            )
            study.file_path_encrypted = enc_path
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("DICOM encryption failed for study %s (viewer frames are ready): %s", study_id, exc)

        _notify_dicom_ready(study, study.user_id)
        logger.info("DICOM study %s processed (%d frames)", study.study_uid, study.num_instances)
        return {"status": "ready", "study_uid": study.study_uid, "num_instances": study.num_instances}

    except DicomParseError as exc:
        logger.warning("DICOM parse failed for study %s: %s", study_id, exc)
        db.rollback()
        _mark_study_failed(db, study_id, str(exc))
        return {"status": "failed", "error": str(exc)}
    except IntegrityError as exc:
        logger.warning("DICOM integrity error for study %s: %s", study_id, exc)
        db.rollback()
        message = friendly_integrity_error(exc) or "Конфликт данных DICOM (дубликат)."
        _mark_study_failed(db, study_id, message)
        return {"status": "failed", "error": message}
    except Exception as exc:
        logger.exception("DICOM processing failed for study %s: %s", study_id, exc)
        db.rollback()
        message = friendly_integrity_error(exc) if isinstance(exc, IntegrityError) else str(exc)
        _mark_study_failed(db, study_id, message)
        return {"status": "failed", "error": message}
    finally:
        db.close()
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
