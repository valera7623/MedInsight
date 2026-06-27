"""Validation and confidence scoring for AI parser output."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.prompts.medical_parser import AI_PARSER_JSON_SCHEMA_KEYS

logger = logging.getLogger(__name__)

LIST_FIELDS = (
    "diagnoses",
    "medications",
    "dates",
    "doctors",
    "recommendations",
    "risk_factors",
    "lab_results",
    "departments",
)


class AIParserValidator:
    """Validate GPT structured output before persisting to Document.parsed_data."""

    def validate(self, result: dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            logger.warning("AI parser result is not a dict")
            return False

        for key in AI_PARSER_JSON_SCHEMA_KEYS:
            if key not in result:
                logger.warning("AI parser missing key: %s", key)
                return False

        for key in LIST_FIELDS:
            if not isinstance(result.get(key), list):
                logger.warning("AI parser field %s must be a list", key)
                return False

        if not isinstance(result.get("summary"), str):
            logger.warning("AI parser summary must be a string")
            return False

        confidence = self.compute_confidence(result)
        result["_confidence"] = confidence

        threshold = settings.AI_PARSER_CONFIDENCE_THRESHOLD
        if confidence < threshold:
            has_content = bool(result.get("summary") or result.get("diagnoses") or result.get("medications"))
            if not has_content:
                logger.warning(
                    "AI parser confidence %.2f below threshold %.2f and no core fields",
                    confidence,
                    threshold,
                )
                return False
            logger.info(
                "AI parser confidence %.2f below threshold %.2f but core fields present — accepting",
                confidence,
                threshold,
            )
        return True

    def compute_confidence(self, result: dict[str, Any]) -> float:
        score = 0.0
        if result.get("diagnoses"):
            score += 0.22
        if result.get("medications"):
            score += 0.18
        if (result.get("summary") or "").strip():
            score += 0.2
        if result.get("dates"):
            score += 0.1
        if result.get("doctors"):
            score += 0.08
        if result.get("recommendations"):
            score += 0.12
        if result.get("lab_results"):
            score += 0.05
        if result.get("risk_factors"):
            score += 0.03
        if result.get("departments"):
            score += 0.02
        return round(min(1.0, score), 2)

    def normalize_for_storage(self, result: dict[str, Any]) -> dict[str, Any]:
        """Strip internal meta keys; keep clinical structure only."""
        stored = {key: result.get(key, [] if key != "summary" else "") for key in AI_PARSER_JSON_SCHEMA_KEYS}
        if result.get("_model"):
            stored["ai_model"] = result["_model"]
        stored["parser"] = "ai"
        return stored

    def log_validation_errors(self, document_id: int, result: dict[str, Any]) -> None:
        logger.error(
            "AI parse validation failed for document %s: confidence=%s keys=%s",
            document_id,
            result.get("_confidence"),
            list(result.keys()) if isinstance(result, dict) else type(result),
        )
