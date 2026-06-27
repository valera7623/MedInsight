"""Hybrid medical document parser: classic text extraction + GPT structuring."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.prompts.medical_parser import (
    AI_PARSER_JSON_SCHEMA_KEYS,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from app.services.openai_client import OpenAIClientError, chat_completion_json
from app.services.parser import parse_document, parse_document_from_bytes

logger = logging.getLogger(__name__)


def empty_ai_result(*, model: str = "none") -> dict[str, Any]:
    return {
        "diagnoses": [],
        "medications": [],
        "dates": [],
        "doctors": [],
        "summary": "",
        "recommendations": [],
        "risk_factors": [],
        "lab_results": [],
        "departments": [],
        "_confidence": 0.0,
        "_model": model,
    }


class AIParser:
    """Extract raw text with python-docx/PyPDF2, structure with GPT."""

    def __init__(self) -> None:
        self.model = settings.AI_PARSER_MODEL or settings.OPENAI_MODEL
        self.enabled = settings.AI_PARSER_ENABLED
        self.max_tokens = settings.AI_PARSER_MAX_TOKENS

    @property
    def is_available(self) -> bool:
        return bool(self.enabled and settings.OPENAI_API_KEY)

    def extract_raw_text(self, file_path: str) -> str:
        return parse_document(file_path)

    def extract_raw_text_from_bytes(self, content: bytes, filename: str) -> str:
        return parse_document_from_bytes(content, filename)

    async def parse_document(self, file_path: str, document_type: str = "discharge") -> dict[str, Any]:
        text = self.extract_raw_text(file_path)
        return await self.parse_text(text, document_type)

    async def parse_text(self, text: str, document_type: str = "discharge") -> dict[str, Any]:
        if not self.is_available or not text.strip():
            return empty_ai_result()

        prompt = build_user_prompt(text, document_type)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await chat_completion_json(
                messages, model=self.model, max_tokens=self.max_tokens, temperature=0.3
            )
            result = self._normalize_gpt_payload(raw)
            result["_model"] = self.model
            if "_confidence" not in result:
                result["_confidence"] = 0.85 if result.get("summary") or result.get("diagnoses") else 0.0
            return result
        except OpenAIClientError as exc:
            logger.error("AI parser GPT error: %s", exc)
            return empty_ai_result(model=self.model)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI parser unexpected error: %s", exc)
            return empty_ai_result(model=self.model)

    async def extract_entities(self, text: str, document_type: str = "discharge") -> dict[str, Any]:
        parsed = await self.parse_text(text, document_type)
        return {
            "diagnoses": parsed.get("diagnoses", []),
            "medications": parsed.get("medications", []),
            "dates": parsed.get("dates", []),
            "doctors": parsed.get("doctors", []),
            "lab_results": parsed.get("lab_results", []),
            "departments": parsed.get("departments", []),
        }

    async def extract_summary(self, text: str, document_type: str = "discharge") -> str:
        parsed = await self.parse_text(text, document_type)
        return str(parsed.get("summary") or "")

    async def extract_recommendations(self, text: str, document_type: str = "discharge") -> list[str]:
        parsed = await self.parse_text(text, document_type)
        recs = parsed.get("recommendations") or []
        return [str(r) for r in recs if r]

    async def extract_risk_factors(self, text: str, document_type: str = "discharge") -> list[str]:
        parsed = await self.parse_text(text, document_type)
        risks = parsed.get("risk_factors") or []
        return [str(r) for r in risks if r]

    def _normalize_gpt_payload(self, raw: dict[str, Any]) -> dict[str, Any]:
        result = empty_ai_result(model=self.model)
        for key in AI_PARSER_JSON_SCHEMA_KEYS:
            if key not in raw:
                continue
            value = raw[key]
            if key == "summary":
                result[key] = str(value or "")
            elif isinstance(value, list):
                result[key] = value
            else:
                logger.debug("AI parser ignoring non-list field %s=%r", key, value)
        return result


def parse_document_path(file_path: str, document_type: str = "discharge") -> dict[str, Any]:
    """Sync helper for Celery — classic text + optional AI structure."""
    import asyncio

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document file not found: {file_path}")

    parser = AIParser()
    text = parser.extract_raw_text(file_path)
    if parser.is_available:
        ai_data = asyncio.run(parser.parse_text(text, document_type))
    else:
        ai_data = empty_ai_result()
    ai_data["full_text"] = text
    return ai_data
