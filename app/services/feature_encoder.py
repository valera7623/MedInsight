"""Flatten nested patient feature dicts into a fixed tabular vector for ML/SHAP."""

from __future__ import annotations

from typing import Any

import numpy as np

# Stable feature order — required for SHAP consistency across requests.
FEATURE_NAMES: list[str] = [
    "age",
    "gender_male",
    "gender_female",
    "diagnosis_count",
    "medication_count",
    "document_count",
    "dicom_study_count",
    "findings_count",
    "impressions_count",
    "abnormal_imaging",
    "tumor_count",
    "guideline_alert_count",
    "polypharmacy",
    "elderly",
    "multi_morbidity",
]

_ABNORMAL_KEYWORDS = (
    "mass", "fracture", "опухол", "перелом", "кровоизлиян", "malignan", "abnormal",
)


def encode_features(features: dict[str, Any]) -> tuple[np.ndarray, list[str]]:
    """Return (1, n_features) float array and feature names."""
    age = float(features.get("age") or 50)
    gender = str(features.get("gender") or "").lower()
    diagnoses = features.get("diagnoses") or []
    medications = features.get("medications") or []
    dicom = features.get("dicom") or {}
    findings = dicom.get("findings") or []
    findings_text = " ".join(str(f) for f in findings).lower()
    abnormal = int(any(kw in findings_text for kw in _ABNORMAL_KEYWORDS))
    tumors = dicom.get("measurements", {}).get("tumors") or []

    row = [
        age,
        float("муж" in gender or gender == "m"),
        float("жен" in gender or gender == "f"),
        float(len(diagnoses)),
        float(len(medications)),
        float(features.get("document_count") or 0),
        float(dicom.get("study_count") or 0),
        float(len(findings)),
        float(len(dicom.get("impressions") or [])),
        float(abnormal),
        float(len(tumors) if isinstance(tumors, list) else 0),
        float(len(dicom.get("guideline_alignment") or [])),
        float(len(medications) >= 5),
        float(age >= 65),
        float(len(diagnoses) >= 3),
    ]
    return np.array([row], dtype=np.float64), list(FEATURE_NAMES)


def encode_batch(feature_dicts: list[dict[str, Any]]) -> tuple[np.ndarray, list[str]]:
    if not feature_dicts:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float64), list(FEATURE_NAMES)
    rows = [encode_features(f)[0][0] for f in feature_dicts]
    return np.vstack(rows), list(FEATURE_NAMES)


def heuristic_readmission_risk(features: dict[str, Any]) -> float:
    """Pseudo-label for model calibration (0–100), mirrors rule-based logic."""
    age = int(features.get("age") or 50)
    diagnoses = features.get("diagnoses") or []
    medications = features.get("medications") or []
    dicom = features.get("dicom") or {}
    findings = dicom.get("findings") or []
    readmission = min(95, 15 + len(diagnoses) * 8 + max(0, age - 60) // 2)
    abnormal = any(
        w in " ".join(str(f) for f in findings).lower() for w in _ABNORMAL_KEYWORDS
    )
    if abnormal:
        readmission = min(95, readmission + 10)
    tumors = dicom.get("measurements", {}).get("tumors") or []
    if tumors:
        readmission = min(95, readmission + 5)
    return float(readmission)
