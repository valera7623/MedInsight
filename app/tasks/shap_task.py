"""Async SHAP value computation for predictions."""

from __future__ import annotations

import logging

from app.config import settings
from app.database import SessionLocal
from app.models import Prediction
from app.services.shap_explainer import attach_shap_to_prediction_dict, get_shap_explainer
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.shap_task.compute_shap_values_task")
def compute_shap_values_task(self, prediction_id: int) -> dict:
    """Compute and persist local SHAP values for a prediction."""
    if not settings.SHAP_ENABLED:
        return {"status": "skipped", "reason": "SHAP disabled"}

    db = SessionLocal()
    try:
        prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first()
        if not prediction:
            return {"status": "failed", "error": "Prediction not found"}

        features = prediction.features or {}
        pred_data = dict(prediction.prediction or {})

        shap_local = get_shap_explainer().explain_local(
            features, prediction_id=prediction_id, use_cache=False
        )
        pred_data = attach_shap_to_prediction_dict(features, pred_data, prediction_id=prediction_id)
        pred_data["shap"] = {"local": shap_local, "status": "ready", "task_id": self.request.id}

        prediction.prediction = pred_data
        if pred_data.get("ml"):
            probs = dict(prediction.probabilities or {})
            probs["ml_high_readmission"] = pred_data["ml"].get("probability_high_readmission")
            prediction.probabilities = probs

        db.commit()
        logger.info("SHAP computed for prediction %s", prediction_id)
        return {"status": "completed", "prediction_id": prediction_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("SHAP task failed for prediction %s: %s", prediction_id, exc)
        if prediction := db.query(Prediction).filter(Prediction.id == prediction_id).first():
            pdata = dict(prediction.prediction or {})
            pdata["shap"] = {"status": "failed", "error": str(exc)}
            prediction.prediction = pdata
            db.commit()
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="app.tasks.shap_task.refresh_global_shap_cache")
def refresh_global_shap_cache(tenant_id: int) -> dict:
    """Pre-warm global SHAP summary cache for a tenant."""
    if not settings.SHAP_ENABLED:
        return {"status": "skipped"}
    try:
        data = get_shap_explainer().explain_global(tenant_id, use_cache=False)
        return {"status": "completed", "features": len(data.get("summary_bar", []))}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Global SHAP refresh failed for tenant %s: %s", tenant_id, exc)
        return {"status": "failed", "error": str(exc)}
