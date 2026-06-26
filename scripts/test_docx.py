#!/usr/bin/env python3
"""Тест генерации DOCX карточки пациента."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.docx_generator import DocxGenerator  # noqa: E402


def test_generate_patient_card() -> str:
    patient_data = {
        "full_name": "Петров Иван Сергеевич",
        "birth_date": "15.05.1980",
        "gender": "Мужской",
        "phone": "+7 (999) 123-45-67",
        "email": "ivan@example.com",
        "department": "Кардиология",
    }

    lab_results = [
        {"name": "Глюкоза", "value": "5.2", "reference": "3.5-6.1", "status": "норма"},
        {"name": "Холестерин общий", "value": "6.5", "reference": "3.0-5.2", "status": "повышен"},
        {"name": "Гемоглобин", "value": "145", "reference": "130-160", "status": "норма"},
        {"name": "Лейкоциты", "value": "4.5", "reference": "4.0-9.0", "status": "норма"},
        {"name": "СОЭ", "value": "25", "reference": "2-15", "status": "повышен"},
    ]

    diagnoses = [
        {"code": "I10", "name": "Гипертоническая болезнь"},
        {"code": "E11.9", "name": "Сахарный диабет 2 типа"},
    ]

    medications = [
        {"name": "Эналаприл", "dosage": "10 мг", "frequency": "1 раз в день", "prescribed_date": "10.01.2026"},
        {"name": "Метформин", "dosage": "500 мг", "frequency": "2 раза в день", "prescribed_date": "10.01.2026"},
    ]

    predictions = [
        {"type": "Риск реадмиссии", "risk": 42, "factors": ["Возраст > 65 лет", "Диабет 2 типа"]},
        {"type": "Риск осложнений", "risk": 35, "factors": ["Гипертония", "Повышенный холестерин"]},
    ]

    dicom_studies = [
        {
            "modality": "CT",
            "body_part": "Chest",
            "study_description": "КТ грудной клетки",
            "study_date": "20.01.2026",
            "num_series": 3,
            "num_instances": 142,
        }
    ]

    anamnesis = [
        "Жалобы на периодическое повышение артериального давления",
        "Хронический пиелонефрит в анамнезе",
    ]

    buffer = DocxGenerator.build_patient_card_bytes(
        patient_data=patient_data,
        lab_results=lab_results,
        diagnoses=diagnoses,
        medications=medications,
        predictions=predictions,
        dicom_studies=dicom_studies,
        anamnesis=anamnesis,
        header_text="MedInsight Demo Clinic",
        footer_text="MedInsight Demo Clinic",
        watermark="MedInsight",
    )

    output_path = Path("patient_card_sample.docx")
    output_path.write_bytes(buffer.getvalue())

    if not output_path.exists() or output_path.stat().st_size < 1000:
        raise SystemExit("DOCX file was not created or is too small")

    print(f"Карточка пациента сохранена: {output_path.resolve()} ({output_path.stat().st_size} bytes)")
    return str(output_path)


if __name__ == "__main__":
    test_generate_patient_card()
