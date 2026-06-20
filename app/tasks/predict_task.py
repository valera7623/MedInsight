import logging
from datetime import datetime

from app.database import SessionLocal
from app.models import AnalysisJob
from app.services.predictor import predict_risk
from app.services.self_healing import with_self_healing
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@with_self_healing("predictor")
def _run_prediction(db, *, patient_id: int, user_id: int, analysis_id: int, tenant_id: int | None):
    return predict_risk(db, patient_id=patient_id, user_id=user_id, analysis_id=analysis_id, tenant_id=tenant_id)


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
