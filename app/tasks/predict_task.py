import asyncio
import logging
from datetime import datetime

from app.config import settings
from app.database import SessionLocal
from app.models import AnalysisJob, Patient, User
from app.services.predictor import predict_risk, predict_risk_with_dicom
from app.services.self_healing import with_self_healing
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _notify_prediction_ready(db, job: AnalysisJob, prediction_id: int) -> None:
    """Send the 'prediction ready' email from the (sync) Celery worker."""
    if not settings.EMAIL_PREDICTION_READY_ENABLED:
        return
    try:
        user = db.query(User).filter(User.id == job.user_id).first()
        if not user or not user.email:
            return
        patient = db.query(Patient).filter(Patient.id == job.patient_id).first()
        patient_name = f"{patient.last_name} {patient.first_name}".strip() if patient else "пациент"

        from app.services.email import get_email_service

        asyncio.run(
            get_email_service().send_prediction_ready_email(user.email, patient_name, prediction_id)
        )
    except Exception as exc:  # noqa: BLE001 — notifications must not fail the task
        logger.warning("Prediction-ready email failed for job %s: %s", job.id, exc)


def _telegram_prediction_ready(db, job: AnalysisJob, prediction) -> None:
    """Send Telegram notification for a completed prediction."""
    if not settings.TELEGRAM_BOT_ENABLED:
        return
    try:
        patient = db.query(Patient).filter(Patient.id == job.patient_id).first()
        patient_name = f"{patient.last_name} {patient.first_name}".strip() if patient else "пациент"
        pred = prediction.prediction or {}
        from app.bot.services.notification_service import get_notification_service

        get_notification_service().send_prediction_ready_sync(
            user_id=job.user_id,
            patient_name=patient_name,
            prediction_id=prediction.id,
            patient_id=job.patient_id,
            risk=round(float(pred.get("readmission_risk", 0))),
            confidence=round(float(prediction.confidence_score or 0), 2),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram prediction notification failed for job %s: %s", job.id, exc)


def _ws_prediction_ready(job: AnalysisJob, prediction) -> None:
    """Push real-time WebSocket events for a completed prediction."""
    try:
        from app.websocket.events import (
            EVENT_ANALYSIS_COMPLETED,
            EVENT_PREDICTION_READY,
            publish_event,
        )

        pred = prediction.prediction or {}
        data = {
            "patient_id": job.patient_id,
            "prediction_id": prediction.id,
            "type": prediction.type,
            "risk": round(float(pred.get("readmission_risk", 0))),
            "confidence": round(float(prediction.confidence_score or 0), 2),
        }
        publish_event(EVENT_PREDICTION_READY, data, user_id=job.user_id, tenant_id=job.tenant_id)
        publish_event(
            EVENT_ANALYSIS_COMPLETED,
            {"patient_id": job.patient_id, "analysis_id": job.id, "type": "predict"},
            user_id=job.user_id, tenant_id=job.tenant_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("WS prediction event failed for job %s: %s", job.id, exc)


@with_self_healing("predictor")
def _run_prediction(db, *, patient_id: int, user_id: int, analysis_id: int, tenant_id: int | None):
    return predict_risk(db, patient_id=patient_id, user_id=user_id, analysis_id=analysis_id, tenant_id=tenant_id)


@with_self_healing("predictor")
def _run_prediction_dicom(db, *, patient_id: int, user_id: int, analysis_id: int, tenant_id: int | None):
    return predict_risk_with_dicom(
        db, patient_id=patient_id, user_id=user_id, analysis_id=analysis_id, tenant_id=tenant_id
    )


@celery_app.task(bind=True, name="app.tasks.predict_task.predict_risk_dicom_task")
def predict_risk_dicom_task(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.error("Analysis job %s not found", job_id)
            return {"status": "failed", "error": "Job not found"}

        job.status = "processing"
        job.celery_task_id = self.request.id
        db.commit()

        prediction = _run_prediction_dicom(
            db,
            patient_id=job.patient_id,
            user_id=job.user_id,
            analysis_id=job.id,
            tenant_id=job.tenant_id,
        )

        job.status = "completed"
        job.result = {
            "prediction_id": prediction.id,
            "prediction": prediction.prediction,
            "probabilities": prediction.probabilities,
            "confidence_score": prediction.confidence_score,
            "dicom_sources": (prediction.prediction or {}).get("dicom_sources", []),
            "shap": (prediction.prediction or {}).get("shap"),
            "ml": (prediction.prediction or {}).get("ml"),
        }
        job.completed_at = datetime.utcnow()
        db.commit()

        try:
            from app.tasks.webhook_task import fire_event

            fire_event(
                "prediction.ready",
                job.tenant_id,
                patient_id=job.patient_id,
                analysis_id=job.id,
                prediction_id=prediction.id,
                result=prediction.prediction,
            )
        except Exception as hook_exc:
            logger.warning("Webhook dispatch failed for DICOM prediction job %s: %s", job_id, hook_exc)

        _notify_prediction_ready(db, job, prediction.id)
        _telegram_prediction_ready(db, job, prediction)
        _ws_prediction_ready(job, prediction)

        logger.info("DICOM prediction completed for patient %s (job %s)", job.patient_id, job_id)
        return {"status": "completed", "prediction_id": prediction.id}

    except Exception as exc:
        logger.exception("DICOM predict task failed for job %s: %s", job_id, exc)
        if job := db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first():
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
        return {"status": "failed", "error": str(exc)}

    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.predict_task.predict_risk_task")
def predict_risk_task(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.error("Analysis job %s not found", job_id)
            return {"status": "failed", "error": "Job not found"}

        job.status = "processing"
        job.celery_task_id = self.request.id
        db.commit()

        prediction = _run_prediction(
            db,
            patient_id=job.patient_id,
            user_id=job.user_id,
            analysis_id=job.id,
            tenant_id=job.tenant_id,
        )

        job.status = "completed"
        job.result = {
            "prediction_id": prediction.id,
            "prediction": prediction.prediction,
            "probabilities": prediction.probabilities,
            "confidence_score": prediction.confidence_score,
            "shap": (prediction.prediction or {}).get("shap"),
            "ml": (prediction.prediction or {}).get("ml"),
        }
        job.completed_at = datetime.utcnow()
        db.commit()

        try:
            from app.tasks.webhook_task import fire_event

            fire_event(
                "prediction.ready",
                job.tenant_id,
                patient_id=job.patient_id,
                analysis_id=job.id,
                prediction_id=prediction.id,
                result=prediction.prediction,
            )
        except Exception as hook_exc:
            logger.warning("Webhook dispatch failed for prediction job %s: %s", job_id, hook_exc)

        _notify_prediction_ready(db, job, prediction.id)
        _telegram_prediction_ready(db, job, prediction)
        _ws_prediction_ready(job, prediction)

        logger.info("Prediction completed for patient %s (job %s)", job.patient_id, job_id)
        return {"status": "completed", "prediction_id": prediction.id}

    except Exception as exc:
        logger.exception("Predict task failed for job %s: %s", job_id, exc)
        if job := db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first():
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
        return {"status": "failed", "error": str(exc)}

    finally:
        db.close()
