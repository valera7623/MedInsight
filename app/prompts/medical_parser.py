"""Prompts for GPT-based medical document structuring."""

from __future__ import annotations

SYSTEM_PROMPT = """
Ты — медицинский ассистент, специалист по извлечению структурированных данных из медицинских документов на русском языке.

Извлекай информацию из текста и возвращай ТОЛЬКО JSON со следующей структурой (без markdown и комментариев):

{
  "diagnoses": [
    {"code": "код МКБ-10 или '—'", "name": "название диагноза", "type": "основной или сопутствующий"}
  ],
  "medications": [
    {"name": "название препарата", "dosage": "дозировка", "frequency": "частота приёма"}
  ],
  "dates": [
    {"type": "admission | discharge | birth | other", "value": "YYYY-MM-DD"}
  ],
  "doctors": [
    {"name": "ФИО врача", "specialty": "специальность"}
  ],
  "summary": "краткое изложение (2-3 предложения)",
  "recommendations": ["рекомендация 1", "рекомендация 2"],
  "risk_factors": ["фактор 1", "фактор 2"],
  "lab_results": [
    {"name": "название показателя", "value": "значение", "reference": "референс", "status": "норма | повышено | понижено | —"}
  ],
  "departments": ["отделение"]
}

Правила:
- Если поле отсутствует в тексте — пустой массив [] или пустая строка для summary.
- Даты нормализуй в ISO YYYY-MM-DD.
- Не выдумывай данные, которых нет в тексте.
- Диагнозы различай основной и сопутствующий по формулировкам документа.
""".strip()

FEW_SHOT_EXAMPLES: dict[str, str] = {
    "discharge": """
Пример входа:
"Диагноз: гипертоническая болезнь (I10). Сопутствующий: сахарный диабет 2 типа (E11.9).
Лечение: эналаприл 10 мг 1 раз в день. Госпитализация: 15.06.2026. Выписка: 20.06.2026.
Лечащий врач: Иванов И.И., кардиолог. Рекомендовано: контроль давления, диета."

Пример ответа:
{
  "diagnoses": [
    {"code": "I10", "name": "Гипертоническая болезнь", "type": "основной"},
    {"code": "E11.9", "name": "Сахарный диабет 2 типа", "type": "сопутствующий"}
  ],
  "medications": [
    {"name": "Эналаприл", "dosage": "10 мг", "frequency": "1 раз в день"}
  ],
  "dates": [
    {"type": "admission", "value": "2026-06-15"},
    {"type": "discharge", "value": "2026-06-20"}
  ],
  "doctors": [
    {"name": "Иванов И.И.", "specialty": "кардиолог"}
  ],
  "summary": "Пациент с гипертонической болезнью и сахарным диабетом 2 типа. Проведено лечение эналаприлом.",
  "recommendations": ["Контроль давления", "Диета"],
  "risk_factors": [],
  "lab_results": [],
  "departments": []
}
""".strip(),
    "lab": """
Пример: извлекай lab_results, diagnoses (если указаны), dates, summary.
""".strip(),
    "referral": """
Пример: извлекай diagnoses, doctors, recommendations, departments, summary.
""".strip(),
}

AI_PARSER_JSON_SCHEMA_KEYS = (
    "diagnoses",
    "medications",
    "dates",
    "doctors",
    "summary",
    "recommendations",
    "risk_factors",
    "lab_results",
    "departments",
)


def build_user_prompt(text: str, document_type: str = "discharge") -> str:
    examples = FEW_SHOT_EXAMPLES.get(document_type, FEW_SHOT_EXAMPLES["discharge"])
    trimmed = text.strip()
    if len(trimmed) > 15000:
        trimmed = trimmed[:15000] + "\n\n[... текст обрезан ...]"
    return (
        f"Тип документа: {document_type}\n\n"
        f"Few-shot пример:\n{examples}\n\n"
        f"Текст для анализа:\n{trimmed}\n\n"
        "Верни JSON в указанной схеме."
    )
