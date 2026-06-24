"""SHAP explainability for readmission classification models."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

import numpy as np

from app.config import settings
from app.core.redis import get_redis
from app.services.feature_encoder import encode_features
from app.services.ml_risk_model import get_background_matrix, get_readmission_model, predict_readmission_proba

logger = logging.getLogger(__name__)

TargetType = Literal["readmission"]


def _normalize_shap_matrix(shap_values: Any, sample_count: int) -> np.ndarray:
    """Return (n_samples, n_features) SHAP matrix for the positive class."""
    if isinstance(shap_values, list):
        sv = shap_values[1] if len(shap_values) > 1 else shap_values[0]
    else:
        sv = shap_values
    sv = np.asarray(sv)
    if sv.ndim == 3:
        # Newer SHAP: (samples, features, classes)
        sv = sv[:, :, 1] if sv.shape[2] > 1 else sv[:, :, 0]
    if sv.ndim == 1:
        sv = sv.reshape(1, -1)
    return sv


class ShapExplainerService:
    """Local and global SHAP explanations with Redis caching."""

    def __init__(self) -> None:
        self._explainer = None
        self._model_id: str | None = None

    def _cache_key_local(self, prediction_id: int) -> str:
        return f"shap:local:{prediction_id}"

    def _cache_key_global(self, tenant_id: int, target: str) -> str:
        model_type = settings.SHAP_MODEL_TYPE
        return f"shap:global:{tenant_id}:{target}:{model_type}"

    def _cache_get(self, key: str) -> dict | None:
        client = get_redis()
        if client is None:
            return None
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("SHAP cache get failed: %s", exc)
            return None

    def _cache_set(self, key: str, payload: dict) -> None:
        client = get_redis()
        if client is None:
            return
        try:
            client.setex(key, settings.SHAP_CACHE_TTL_SECONDS, json.dumps(payload, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.debug("SHAP cache set failed: %s", exc)

    def _get_explainer(self):
        if not settings.SHAP_ENABLED:
            raise RuntimeError("SHAP is disabled")
        try:
            import shap
        except ImportError as exc:
            raise RuntimeError("shap package is not installed") from exc

        clf = get_readmission_model()
        model_id = hashlib.md5(repr(type(clf).__name__).encode()).hexdigest()[:12]
        if self._explainer is not None and self._model_id == model_id:
            return self._explainer

        self._explainer = shap.TreeExplainer(clf)
        self._model_id = model_id
        return self._explainer

    def explain_local(
        self,
        features: dict[str, Any],
        *,
        prediction_id: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Local SHAP values for a single patient feature dict."""
        if prediction_id and use_cache:
            cached = self._cache_get(self._cache_key_local(prediction_id))
            if cached:
                cached["cached"] = True
                return cached

        ml_pred = predict_readmission_proba(features)
        X, feature_names = encode_features(features)
        explainer = self._get_explainer()
        shap_values = explainer.shap_values(X)

        if isinstance(shap_values, list):
            sv_row = np.asarray(shap_values[1] if len(shap_values) > 1 else shap_values[0]).reshape(-1)
        else:
            sv_arr = np.asarray(shap_values)
            if sv_arr.ndim == 3:
                sv_row = sv_arr[0, :, 1] if sv_arr.shape[2] > 1 else sv_arr[0, :, 0]
            else:
                sv_row = sv_arr.reshape(-1) if sv_arr.ndim == 1 else sv_arr[0]

        base_value = explainer.expected_value
        if isinstance(base_value, (list, np.ndarray)):
            base_value = float(base_value[1] if len(base_value) > 1 else base_value[0])
        else:
            base_value = float(base_value)

        contributions = [
            {
                "feature": name,
                "value": float(X[0, i]),
                "shap": float(sv_row[i]),
            }
            for i, name in enumerate(feature_names)
        ]
        contributions.sort(key=lambda x: abs(x["shap"]), reverse=True)

        payload = {
            "target": "readmission",
            "model_type": settings.SHAP_MODEL_TYPE,
            "base_value": base_value,
            "output_value": base_value + float(sv_row.sum()),
            "ml_prediction": ml_pred,
            "contributions": contributions,
            "top_features": contributions[:10],
            "waterfall": {
                "base_value": base_value,
                "steps": contributions[:15],
                "output_value": base_value + float(sv_row.sum()),
            },
            "cached": False,
        }

        if prediction_id:
            self._cache_set(self._cache_key_local(prediction_id), payload)
        return payload

    def explain_global(
        self,
        tenant_id: int,
        *,
        target: TargetType = "readmission",
        sample_size: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Global SHAP summary data for frontend visualization (bar + beeswarm)."""
        cache_key = self._cache_key_global(tenant_id, target)
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                cached["cached"] = True
                return cached

        n = sample_size or settings.SHAP_SUMMARY_SAMPLE_SIZE
        X, feature_names = get_background_matrix(n)
        explainer = self._get_explainer()
        shap_values = explainer.shap_values(X)
        sv = _normalize_shap_matrix(shap_values, X.shape[0])

        mean_abs = np.abs(sv).mean(axis=0).flatten()
        order = np.argsort(-mean_abs)
        summary_bar = [
            {"feature": feature_names[int(i)], "mean_abs_shap": float(mean_abs[int(i)])}
            for i in order
        ]

        # Beeswarm sample: up to 500 points per feature (flattened for JSON).
        beeswarm: list[dict[str, float | str]] = []
        max_points = min(X.shape[0], 200)
        for i in order[:15]:
            idx = int(i)
            for row_idx in range(max_points):
                beeswarm.append(
                    {
                        "feature": feature_names[idx],
                        "feature_value": float(X[row_idx, idx]),
                        "shap_value": float(sv[row_idx, idx]),
                    }
                )

        payload = {
            "target": target,
            "tenant_id": tenant_id,
            "model_type": settings.SHAP_MODEL_TYPE,
            "sample_size": int(X.shape[0]),
            "feature_names": feature_names,
            "summary_bar": summary_bar,
            "beeswarm": beeswarm,
            "cached": False,
        }
        self._cache_set(cache_key, payload)
        return payload


_service: ShapExplainerService | None = None


def get_shap_explainer() -> ShapExplainerService:
    global _service
    if _service is None:
        _service = ShapExplainerService()
    return _service


def attach_shap_to_prediction_dict(
    features: dict[str, Any],
    prediction_data: dict[str, Any],
    *,
    prediction_id: int | None = None,
) -> dict[str, Any]:
    """Merge ML prediction + local SHAP into the prediction JSON blob."""
    if not settings.SHAP_ENABLED:
        return prediction_data

    try:
        ml = predict_readmission_proba(features)
        shap_local = get_shap_explainer().explain_local(features, prediction_id=prediction_id)
        prediction_data = dict(prediction_data)
        prediction_data["ml"] = ml
        prediction_data["shap"] = {
            "local": shap_local,
            "status": "ready",
        }
        prediction_data["source"] = prediction_data.get("source", "unknown") + "+shap"
    except Exception as exc:  # noqa: BLE001
        logger.warning("SHAP attachment failed: %s", exc)
        prediction_data = dict(prediction_data)
        prediction_data["shap"] = {"status": "failed", "error": str(exc)}
    return prediction_data
