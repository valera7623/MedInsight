#!/usr/bin/env python3
"""Test hybrid AI medical document parser."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AI_PARSER_ENABLED", "true")

SAMPLE_TEXT = """
Выписка из истории болезни.
Пациент: Иванов Иван Иванович, 01.01.1976.
Диагноз: Гипертоническая болезнь (I10), сахарный диабет 2 типа (E11.9).
Поступил: 15.06.2026. Выписан: 20.06.2026.
Лечение: Эналаприл 10 мг 1 раз в день, Метформин 500 мг 2 раза в день.
Рекомендовано: контроль артериального давления, диета с ограничением углеводов.
Лечащий врач: Петров П.П., кардиолог.
Отделение: Кардиология.
"""


async def test_ai_parser() -> int:
    from app.config import settings
    from app.services.ai_parser import AIParser
    from app.services.ai_parser_validator import AIParserValidator

    print("=== AI Parser Test ===")
    print(f"  AI_PARSER_ENABLED: {settings.AI_PARSER_ENABLED}")
    print(f"  OPENAI_API_KEY set: {bool(settings.OPENAI_API_KEY)}")
    print(f"  Model: {settings.AI_PARSER_MODEL}")

    parser = AIParser()
    validator = AIParserValidator()

    if not parser.is_available:
        print("\nSKIP: AI parser unavailable (disabled or no API key)")
        print("Set OPENAI_API_KEY in .env to run live GPT test.")
        return 0

    result = await parser.parse_text(SAMPLE_TEXT, "discharge")
    print("\nRaw GPT result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    ok = validator.validate(result)
    confidence = result.get("_confidence", 0.0)
    print(f"\nValidation: {'PASS' if ok else 'FAIL'} (confidence={confidence})")

    if ok:
        stored = validator.normalize_for_storage(result)
        print("\nStored payload (preview):")
        print(json.dumps(stored, ensure_ascii=False, indent=2))

    entities = await parser.extract_entities(SAMPLE_TEXT, "discharge")
    summary = await parser.extract_summary(SAMPLE_TEXT, "discharge")
    print(f"\nSummary: {summary[:120]}...")
    print(f"Entities diagnoses count: {len(entities.get('diagnoses', []))}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(test_ai_parser()))
