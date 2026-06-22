"""Celery task: process DICOM ZIP archives (multi-file studies)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import DicomFrame, DicomSeries, DicomStudy, Patient
from app.services.dicom_parser import DicomParseError
from app.services.dicom_storage import DicomStorage
from app.services.dicom_zip_processor import DicomZipProcessor, DicomZipError
from app.tasks.celery_app import celery_app
from app.tasks.dicom_task import _notify_dicom_ready

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 100


def _update_progress(task, processed: int, total: int, study_uid: str | None = None) -> None:
    task_id = getattr(getattr(task, "request", None), "id", None)
    if not task_id:
        return
    meta = {"processed": processed, "total": total, "percent": int(processed * 100 / total) if total else 0}
    if study_uid:
        meta["study_uid"] = study_uid
    task.update_state(state="PROGRESS", meta=meta)


@celery_app.task(
    bind=True,
    name="app.tasks.dicom_zip_task.process_dicom_zip",
    soft_time_limit=settings.DICOM_ZIP_TASK_TIMEOUT_SEC,
    time_limit=settings.DICOM_ZIP_TASK_TIMEOUT_SEC + 120,
)
def process_dicom_zip(self, study_id: int, zip_path: str, user_id: int) -> dict:
    db = SessionLocal()
    processor = DicomZipProcessor()
    storage = DicomStorage()
    temp_dir: str | None = None

    try:
        study = db.query(DicomStudy).filter(DicomStudy.id == study_id).first()
        if not study:
            return {"status": "failed", "error": "Study not found"}

        study.status = "processing"
        db.commit()

        entries = processor.iter_zip_dicom_paths(zip_path)
        total_files = len(entries)
        study.total_files = total_files
        db.commit()

        _update_progress(self, 0, total_files, study.study_uid)

        temp_dir = processor.extract_zip(zip_path)
        dicom_files = processor.scan_files(temp_dir)
        if not dicom_files:
            raise DicomZipError("No DICOM files after extraction")

        file_groups = processor.group_files(dicom_files)
        primary_study_uid = max(
            file_groups.keys(),
            key=lambda k: sum(len(files) for files in file_groups[k].values()),
        )
        primary_series_groups = file_groups[primary_study_uid]
        primary_files = [f for files in primary_series_groups.values() for f in files]

        structure = processor.process_study(
            primary_files,
            study.patient_id,
            series_groups=primary_series_groups,
        )
        real_study_uid = structure["study_uid"]

        study.study_uid = real_study_uid
        study.study_date = structure.get("study_date") or study.study_date
        study.study_description = structure.get("study_description")
        study.modality = structure.get("modality")
        study.body_part = structure.get("body_part")
        study.patient_name_dicom = structure.get("patient_name")
        study.patient_id_dicom = structure.get("patient_id_dicom")
        study.num_series = 0
        study.num_instances = 0
        db.commit()

        processed_count = 0
        series_count = 0
        instance_count = 0

        for series_data in structure["series"]:
            series_uid = series_data["series_uid"]
            series = (
                db.query(DicomSeries)
                .filter(DicomSeries.study_id == study.id, DicomSeries.series_uid == series_uid)
                .first()
            )
            if not series:
                series = DicomSeries(
                    study_id=study.id,
                    series_uid=series_uid,
                    series_number=series_data.get("series_number"),
                    series_description=series_data.get("series_description"),
                    modality=series_data.get("modality"),
                    original_filename=Path(series_data.get("original_filename") or "").name or None,
                    num_instances=0,
                )
                db.add(series)
                db.flush()
            series_count += 1

            for inst in series_data["instances"]:
                frame_tuples = [
                    (f["instance_uid"], f["frame_number"], f["png_bytes"]) for f in inst["frames"]
                ]
                image_paths = storage.store_frames(
                    patient_id=study.patient_id,
                    study_uid=real_study_uid,
                    frames=frame_tuples,
                )
                for fmeta, img_path in zip(inst["frames"], image_paths, strict=True):
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
                    instance_count += 1

                series.num_instances += len(inst["frames"])
                processed_count += 1
                study.processed_files = processed_count

            db.commit()
            if processed_count % PROGRESS_EVERY == 0:
                _update_progress(self, processed_count, total_files, real_study_uid)

        try:
            first_dcm = primary_files[0]
            enc_dcm_path = storage.store_encrypted(
                first_dcm,
                tenant_id=study.tenant_id,
                patient_id=study.patient_id,
                study_uid=real_study_uid,
                filename=Path(first_dcm).name,
            )
            study.file_path_encrypted = enc_dcm_path
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("DICOM ZIP encryption failed for study %s: %s", study_id, exc)

        # Additional Study UIDs in same ZIP → separate DicomStudy rows
        for alt_uid, alt_series_groups in file_groups.items():
            if alt_uid == primary_study_uid:
                continue
            alt_files = [f for files in alt_series_groups.values() for f in files]
            try:
                alt_structure = processor.process_study(
                    alt_files,
                    study.patient_id,
                    series_groups=alt_series_groups,
                )
                alt_study = DicomStudy(
                    patient_id=study.patient_id,
                    tenant_id=study.tenant_id,
                    user_id=user_id,
                    study_uid=alt_structure["study_uid"],
                    study_date=alt_structure.get("study_date"),
                    study_description=alt_structure.get("study_description"),
                    modality=alt_structure.get("modality"),
                    body_part=alt_structure.get("body_part"),
                    patient_name_dicom=alt_structure.get("patient_name"),
                    patient_id_dicom=alt_structure.get("patient_id_dicom"),
                    zip_original_path=study.zip_original_path,
                    zip_size_mb=study.zip_size_mb,
                    total_files=len(alt_files),
                    processed_files=len(alt_files),
                    original_filename=study.original_filename,
                    status="ready",
                    num_series=alt_structure["num_series"],
                    num_instances=alt_structure["num_instances"],
                    processed_at=datetime.utcnow(),
                )
                db.add(alt_study)
                db.flush()

                for series_data in alt_structure["series"]:
                    alt_series = DicomSeries(
                        study_id=alt_study.id,
                        series_uid=series_data["series_uid"],
                        series_number=series_data.get("series_number"),
                        series_description=series_data.get("series_description"),
                        modality=series_data.get("modality"),
                        original_filename=Path(series_data.get("original_filename") or "").name or None,
                        num_instances=0,
                    )
                    db.add(alt_series)
                    db.flush()
                    for inst in series_data["instances"]:
                        frame_tuples = [
                            (f["instance_uid"], f["frame_number"], f["png_bytes"]) for f in inst["frames"]
                        ]
                        image_paths = storage.store_frames(
                            patient_id=alt_study.patient_id,
                            study_uid=alt_study.study_uid,
                            frames=frame_tuples,
                        )
                        for fmeta, img_path in zip(inst["frames"], image_paths, strict=True):
                            db.add(
                                DicomFrame(
                                    series_id=alt_series.id,
                                    instance_uid=fmeta["instance_uid"],
                                    frame_number=fmeta["frame_number"],
                                    image_path=img_path,
                                    width=fmeta.get("width"),
                                    height=fmeta.get("height"),
                                    bit_depth=fmeta.get("bit_depth"),
                                    pixel_spacing=fmeta.get("pixel_spacing"),
                                )
                            )
                        alt_series.num_instances += len(inst["frames"])
            except (DicomZipError, DicomParseError) as exc:
                logger.warning("Skipped secondary study %s: %s", alt_uid, exc)

        study.num_series = series_count
        study.num_instances = instance_count
        study.processed_files = total_files
        study.status = "ready"
        study.processed_at = datetime.utcnow()
        study.error_message = None
        db.commit()

        _update_progress(self, total_files, total_files, real_study_uid)
        _notify_dicom_ready(study, user_id)
        logger.info(
            "DICOM ZIP study %s ready: %d series, %d instances from %d files",
            real_study_uid,
            series_count,
            instance_count,
            total_files,
        )
        return {
            "status": "ready",
            "study_uid": real_study_uid,
            "num_series": series_count,
            "num_instances": instance_count,
            "total_files": total_files,
        }

    except Exception as exc:
        logger.exception("DICOM ZIP processing failed for study %s: %s", study_id, exc)
        db.rollback()
        if study := db.query(DicomStudy).filter(DicomStudy.id == study_id).first():
            study.status = "failed"
            study.error_message = str(exc)
            study.processed_at = datetime.utcnow()
            db.commit()
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
        if temp_dir:
            processor.cleanup_temp(temp_dir)
        try:
            Path(zip_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
