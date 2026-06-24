#!/usr/bin/env python3
"""Smoke test for SHAP explainability integration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.feature_encoder import encode_features, heuristic_readmission_risk
from app.services.ml_risk_model import predict_readmission_proba
from app.services.shap_explainer import get_shap_explainer


def main() -> None:
    features = {
        "age": 72,
        "gender": "мужской",
        "diagnoses": ["I10", "E11", "J44"],
        "medications": ["A", "B", "C", "D", "E", "F"],
        "document_count": 4,
        "dicom": {
            "study_count": 2,
            "findings": ["suspicious mass in lung"],
            "impressions": ["follow-up recommended"],
            "measurements": {"tumors": [{"size_mm": 12}]},
            "guideline_alignment": [{"action": "review"}],
        },
    }

    X, names = encode_features(features)
    print(f"✓ Encoded {X.shape[1]} features: {names[:5]}...")

    risk = heuristic_readmission_risk(features)
    print(f"✓ Heuristic readmission risk: {risk}%")

    ml = predict_readmission_proba(features)
    print(f"✓ ML prediction: class={ml.get('predicted_class')} p_high={ml.get('probability_high_readmission'):.3f}")

    local = get_shap_explainer().explain_local(features, prediction_id=999)
    print(f"✓ Local SHAP: base={local['base_value']:.4f} output={local['output_value']:.4f}")
    print(f"  Top feature: {local['top_features'][0]}")

    global_data = get_shap_explainer().explain_global(tenant_id=1)
    print(f"✓ Global SHAP summary: {len(global_data['summary_bar'])} features, beeswarm={len(global_data['beeswarm'])} points")

    print("\nAll SHAP tests passed.")


if __name__ == "__main__":
    main()
