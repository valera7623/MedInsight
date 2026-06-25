"""GPT prompt templates for document-based clinical predictions."""

from __future__ import annotations

from typing import Any

USER_PROMPT_CLINICAL = """Проанализируй данные пациента и оцени риск.

Пациент: {name}, {age} лет, {gender}
Диагнозы: {diagnoses}
Анамнез (перенесённые заболевания): {anamnesis}
Перенесённые операции: {operations}
Лекарства: {medications}

Лабораторные и инфекционные данные:
{lab_results_block}

Заключения УЗИ и визуализации:
{imaging_block}

Учитывай отклонения от нормы в анализах, гинекологический/репродуктивный контекст
(овариальный резерв, эндометрит и т.п.), перенесённые операции и инфекционный скрининг.

Оцени риск реадмиссии (0-100%), риск осложнений (0-100%).
Верни JSON:
{{
  "readmission_risk": 42,
  "complication_risk": 35,
  "factors": ["..."],
  "recommendations": ["..."]
}}"""


def format_lab_results_block(lab_results: dict[str, Any]) -> str:
    if not lab_results:
        return "нет данных"
    lines: list[str] = []
    for name in sorted(lab_results.keys(), key=str.casefold):
        entry = lab_results[name]
        if not isinstance(entry, dict):
            lines.append(f"- {name}: {entry}")
            continue
        value = entry.get("value", "")
        reference = entry.get("reference", "")
        section = entry.get("section", "")
        abnormal = entry.get("abnormal")
        flag = " [ОТКЛОНЕНИЕ]" if abnormal else ""
        section_note = f" ({section})" if section else ""
        ref_note = f", норма: {reference}" if reference else ""
        lines.append(f"- {name}: {value}{ref_note}{section_note}{flag}")
    return "\n".join(lines)


def build_gpt_clinical_prompt(features: dict[str, Any]) -> str:
    operations = features.get("operations") or []
    imaging = features.get("imaging_conclusions") or []
    operations_block = "\n".join(f"- {op}" for op in operations) if operations else "нет данных"
    imaging_block = "\n".join(f"- {c}" for c in imaging) if imaging else "нет данных"

    return USER_PROMPT_CLINICAL.format(
        name=features.get("name", ""),
        age=features.get("age", ""),
        gender=features.get("gender", ""),
        diagnoses=features.get("diagnoses", []),
        anamnesis=features.get("anamnesis", []),
        operations=operations_block,
        medications=features.get("medications", []),
        lab_results_block=format_lab_results_block(features.get("lab_results") or {}),
        imaging_block=imaging_block,
    )
