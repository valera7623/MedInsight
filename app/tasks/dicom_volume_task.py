"""Celery task: build 3D volume from DICOM study frames."""

from __future__ import annotations

import logging

from app.config import settings
from app.database import SessionLocal
from app.services.dicom_volume import DicomVolumeError, DicomVolumeService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.dicom_volume_task.build_volume_from_study",
    soft_time_limit=settings.DICOM_3D_RENDER_TIMEOUT_SECONDS,
    time_limit=settings.DICOM_3D_RENDER_TIMEOUT_SECONDS + 30,
)
def build_volume_from_study(self, study_uid: str) -> dict:
    """Assemble volume data from DicomFrame PNGs and cache in Redis/disk."""
    db = SessionLocal()
    try:
        service = DicomVolumeService(db)
        if service.is_volume_cached(study_uid):
            info = service.get_volume_info(study_uid)
            return {
                "status": "ready",
                "study_uid": study_uid,
                "dimensions": info.get("dimensions"),
                "spacing": info.get("spacing"),
                "orientation": info.get("orientation"),
                "cached": True,
            }

        self.update_state(state="PROGRESS", meta={"step": "loading_frames", "study_uid": study_uid})
        packed = service.build_volume_from_frames(study_uid)
        info = service.get_volume_info(study_uid)

        logger.info(
            "Volume built for study %s — %s slices, %d bytes packed",
            study_uid,
            info.get("num_slices"),
            len(packed),
        )

        return {
            "status": "ready",
            "study_uid": study_uid,
            "dimensions": info.get("dimensions"),
            "spacing": info.get("spacing"),
            "orientation": info.get("orientation"),
            "num_slices": info.get("num_slices"),
        }
    except DicomVolumeError as exc:
        logger.warning("Volume build failed for %s: %s", study_uid, exc)
        return {"status": "failed", "study_uid": study_uid, "error": str(exc)}
    except Exception as exc:
        logger.exception("Volume build error for %s: %s", study_uid, exc)
        return {"status": "failed", "study_uid": study_uid, "error": str(exc)}
    finally:
        db.close()
