"""GPT prompt templates and clinical guidelines for DICOM-enriched predictions."""

from __future__ import annotations

from typing import Any

CLINICAL_GUIDELINES: dict[str, dict[str, Any]] = {
    "CT": {
        "body_parts": {
            "CHEST": {
                "follow_up": [
                    "При подозрении на злокачественное образование лёгкого — консилиум и биопсия",
                    "Контрольная КТ через 3–6 месяцев при неопределённых узлах (Fleischner)",
                ],
                "avoid": ["Повторная КТ без клинических показаний в течение 1 месяца"],
            },
            "HEAD": {
                "follow_up": ["МРТ головного мозга при подозрении на ишемический инсульт"],
                "avoid": ["КТ без контраста при выраженной почечной недостаточности без коррекции"],
            },
            "ABDOMEN": {
                "follow_up": ["УЗИ/МРТ при выявлении объёмных образований печени"],
                "avoid": [],
            },
        },
        "default": {
            "follow_up": ["Корреляция с клиникой и лабораторными данными"],
            "avoid": ["Избыточное лучевое обследование без изменения тактики"],
        },
    },
    "MR": {
        "body_parts": {
            "BRAIN": {
                "follow_up": ["Неврологическое наблюдение, контроль МРТ по показаниям"],
                "avoid": [],
            },
            "SPINE": {
                "follow_up": ["Ортопедическая консультация при компрессии корешков"],
                "avoid": [],
            },
        },
        "default": {
            "follow_up": ["Сопоставление с клинической картиной"],
            "avoid": [],
        },
    },
    "CR": {
        "body_parts": {
            "CHEST": {
                "follow_up": ["КТ грудной клетки при подозрении на инфильтрат/пневмоторакс"],
                "avoid": [],
            },
        },
        "default": {
            "follow_up": ["Повторный снимок при неясной картине"],
            "avoid": [],
        },
    },
}

PREDICT_WITH_CT = (
    "Пациент {age}, {sex}. КТ {body_part}: {findings}. "
    "Размеры: {measurements}. Заключение: {impression}. "
    "Оцени риск {complication}."
)
PREDICT_WITH_MRI = (
    "Пациент {age}, {sex}. МРТ {body_part}: {findings}. "
    "Заключение: {impression}. Оцени риск {complication}."
)
PREDICT_WITH_XRAY = (
    "Пациент {age}, {sex}. Рентген {body_part}: {findings}. "
    "Оцени риск {complication}."
)

SYSTEM_PROMPT_DICOM = (
    "Ты клинический аналитик с доступом к данным визуализации (DICOM). "
    "Учитывай находки, измерения и заключение радиолога. "
    "Отвечай только валидным JSON на русском языке. "
    "Риски — целые числа от 0 до 100."
)

USER_PROMPT_DICOM = """Проанализируй данные пациента и оцени риск.

Пациент: {name}, {age} лет, {gender}
Диагнозы (документы): {diagnoses}
Анамнез: {anamnesis}
Перенесённые операции: {operations}
Лекарства: {medications}
Лабораторные данные: {lab_results}
Заключения УЗИ (документы): {imaging_conclusions}

DICOM-исследования:
{dicom_studies_block}

Измерения (DICOM/аннотации):
{measurements_block}

Находки:
{findings_block}

Заключения радиолога:
{impression_block}

Сопоставление с клиническими рекомендациями:
{guidelines_block}

Оцени риск реадмиссии (0-100%), риск осложнений (0-100%).
Верни JSON:
{{
  "readmission_risk": 42,
  "complication_risk": 35,
  "factors": ["..."],
  "recommendations": ["..."],
  "imaging_notes": ["..."],
  "guideline_alignment": [
    {{"action": "следует выполнить|не следует выполнять|рассмотреть", "recommendation": "...", "rationale": "..."}}
  ]
}}"""


def _normalize_modality(modality: str | None) -> str:
    m = (modality or "").upper()
    if m in {"MR", "MRI"}:
        return "MR"
    if m in {"CR", "DX", "XR"}:
        return "CR"
    if m == "CT":
        return "CT"
    return m or "CT"


def get_modality_prompt_template(modality: str | None) -> str:
    m = _normalize_modality(modality)
    if m == "MR":
        return PREDICT_WITH_MRI
    if m == "CR":
        return PREDICT_WITH_XRAY
    return PREDICT_WITH_CT


def compare_with_guidelines(modality: str | None, body_part: str | None, findings: list[str]) -> list[dict[str, str]]:
    """Map findings to modality-specific guideline recommendations."""
    mod = _normalize_modality(modality)
    guide = CLINICAL_GUIDELINES.get(mod, CLINICAL_GUIDELINES.get("CT", {}))
    bp = (body_part or "").upper().replace(" ", "_")
    part_guide = guide.get("body_parts", {}).get(bp) or guide.get("default", {})
    follow_up = part_guide.get("follow_up", [])
    avoid = part_guide.get("avoid", [])

    findings_text = " ".join(findings).lower()
    results: list[dict[str, str]] = []

    abnormal_keywords = ("mass", "fracture", "malignan", "опухол", "перелом", "инфильтрат", "кровоизлиян")
    has_abnormal = any(k in findings_text for k in abnormal_keywords)

    for rec in follow_up:
        action = "рассмотреть"
        if has_abnormal and any(w in rec.lower() for w in ("биопс", "консилиум", "мрт", "кт")):
            action = "следует выполнить"
        results.append({"action": action, "recommendation": rec, "rationale": f"{mod} {body_part or 'N/A'}"})

    for rec in avoid:
        results.append({"action": "не следует выполнять", "recommendation": rec, "rationale": "профилактика избыточного облучения"})

    if not results:
        results.append(
            {
                "action": "рассмотреть",
                "recommendation": "Корреляция визуализации с клиникой",
                "rationale": "нет специфических рекомендаций для данной модальности",
            }
        )
    return results


def build_gpt_user_prompt(features: dict[str, Any], dicom_bundle: dict[str, Any]) -> str:
    studies = dicom_bundle.get("studies", [])
    studies_lines = []
    for s in studies:
        studies_lines.append(
            f"- {s.get('modality', '?')} {s.get('body_part', '')} "
            f"({s.get('study_date', '')}): {s.get('study_description', '')}"
        )
    dicom_block = "\n".join(studies_lines) if studies_lines else "нет данных"

    measurements = dicom_bundle.get("measurements", {})
    meas_lines = []
    for category, items in measurements.items():
        if isinstance(items, list):
            for item in items:
                meas_lines.append(f"- [{category}] {item}")
        elif isinstance(items, dict):
            for k, v in items.items():
                meas_lines.append(f"- {k}: {v}")
    measurements_block = "\n".join(meas_lines) if meas_lines else "нет измерений"

    findings = dicom_bundle.get("findings", [])
    findings_block = "\n".join(f"- {f}" for f in findings) if findings else "нет находок"

    impressions = dicom_bundle.get("impressions", [])
    impression_block = "\n".join(f"- {i}" for i in impressions) if impressions else "нет заключений"

    guidelines = dicom_bundle.get("guideline_alignment", [])
    guide_lines = [f"- [{g.get('action')}] {g.get('recommendation')}" for g in guidelines]
    guidelines_block = "\n".join(guide_lines) if guide_lines else "нет сопоставления"

    return USER_PROMPT_DICOM.format(
        name=features.get("name", ""),
        age=features.get("age", ""),
        gender=features.get("gender", ""),
        diagnoses=features.get("diagnoses", []),
        anamnesis=features.get("anamnesis", []),
        operations=features.get("operations", []),
        medications=features.get("medications", []),
        lab_results=features.get("lab_results", {}),
        imaging_conclusions=features.get("imaging_conclusions", []),
        dicom_studies_block=dicom_block,
        measurements_block=measurements_block,
        findings_block=findings_block,
        impression_block=impression_block,
        guidelines_block=guidelines_block,
    )
