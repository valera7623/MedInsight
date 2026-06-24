"""Tabular readmission risk classifiers (Random Forest / XGBoost) for SHAP explainability."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from app.config import settings
from app.services.feature_encoder import FEATURE_NAMES, encode_batch, encode_features, heuristic_readmission_risk

logger = logging.getLogger(__name__)

ModelType = Literal["random_forest", "xgboost"]

_model_cache: dict[str, Any] = {}


def _generate_synthetic_dataset(n: int = 800) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    feature_dicts: list[dict] = []
    for _ in range(n):
        age = int(rng.integers(18, 95))
        n_diag = int(rng.integers(0, 8))
        n_med = int(rng.integers(0, 12))
        n_studies = int(rng.integers(0, 4))
        feature_dicts.append(
            {
                "age": age,
                "gender": "мужской" if rng.random() > 0.5 else "женский",
                "diagnoses": [f"D{i}" for i in range(n_diag)],
                "medications": [f"M{i}" for i in range(n_med)],
                "document_count": int(rng.integers(0, 20)),
                "dicom": {
                    "study_count": n_studies,
                    "findings": ["mass detected"] if rng.random() > 0.85 else [],
                    "impressions": [],
                    "measurements": {"tumors": [{}] if rng.random() > 0.9 else []},
                    "guideline_alignment": [],
                },
            }
        )
    X, names = encode_batch(feature_dicts)
    y = np.array([1 if heuristic_readmission_risk(f) >= 50 else 0 for f in feature_dicts], dtype=np.int32)
    return X, y


def _build_xgboost():
    try:
        from xgboost import XGBClassifier
    except ImportError as exc:
        raise RuntimeError("xgboost is not installed") from exc
    return XGBClassifier(
        n_estimators=120,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        eval_metric="logloss",
    )


def _train_model(model_type: ModelType) -> Any:
    X, y = _generate_synthetic_dataset()
    if model_type == "xgboost":
        clf = _build_xgboost()
    else:
        clf = RandomForestClassifier(
            n_estimators=120,
            max_depth=8,
            min_samples_leaf=4,
            random_state=42,
            n_jobs=-1,
        )
    clf.fit(X, y)
    logger.info("Trained %s readmission model on %d synthetic samples", model_type, len(y))
    return clf


def get_readmission_model(*, force_retrain: bool = False) -> Any:
    model_type: ModelType = (
        "xgboost" if settings.SHAP_MODEL_TYPE.lower() == "xgboost" else "random_forest"
    )
    cache_key = f"readmission:{model_type}"

    if not force_retrain and cache_key in _model_cache:
        return _model_cache[cache_key]

    model_path = Path(settings.ML_MODEL_PATH) / f"readmission_{model_type}.joblib"
    if not force_retrain and model_path.is_file():
        try:
            clf = joblib.load(model_path)
            _model_cache[cache_key] = clf
            return clf
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load model from %s: %s", model_path, exc)

    clf = _train_model(model_type)
    try:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(clf, model_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist ML model: %s", exc)

    _model_cache[cache_key] = clf
    return clf


def predict_readmission_proba(features: dict[str, Any]) -> dict[str, Any]:
    """Classify high readmission risk and return probabilities."""
    if not settings.SHAP_ENABLED:
        return {}

    X, feature_names = encode_features(features)
    clf = get_readmission_model()
    proba = clf.predict_proba(X)[0]
    classes = list(clf.classes_)
    high_idx = classes.index(1) if 1 in classes else int(np.argmax(proba))
    p_high = float(proba[high_idx])
    return {
        "model_type": settings.SHAP_MODEL_TYPE,
        "feature_names": feature_names,
        "probability_high_readmission": p_high,
        "probability_low_readmission": float(1.0 - p_high),
        "predicted_class": "high" if p_high >= 0.5 else "low",
        "risk_percent": round(p_high * 100, 1),
    }


def get_background_matrix(n: int = 200) -> tuple[np.ndarray, list[str]]:
    """Background sample for global SHAP / summary plots."""
    n = min(max(n, 10), 500)
    X, _ = _generate_synthetic_dataset(n)
    return X, list(FEATURE_NAMES)
