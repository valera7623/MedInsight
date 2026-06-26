"""Structural templates for DOCX clinical documents."""

from __future__ import annotations

TEMPLATE_PATIENT_CARD = {
    "title": "МЕДИЦИНСКАЯ КАРТОЧКА ПАЦИЕНТА",
    "sections": [
        {
            "key": "patient",
            "title": "ИНФОРМАЦИЯ О ПАЦИЕНТЕ",
            "fields": [
                "full_name",
                "birth_date",
                "gender",
                "phone",
                "email",
                "department",
            ],
        },
        {
            "key": "anamnesis",
            "title": "АНАМНЕЗ",
            "description": "Жалобы и перенесённые заболевания",
        },
        {
            "key": "diagnoses",
            "title": "ДИАГНОЗЫ",
            "columns": ["code", "name"],
        },
        {
            "key": "lab",
            "title": "ЛАБОРАТОРНЫЕ АНАЛИЗЫ",
            "table_headers": ["Показатель", "Значение", "Референсные значения", "Статус"],
        },
        {
            "key": "medications",
            "title": "ЛЕКАРСТВА",
            "table_headers": ["Название", "Дозировка", "Частота", "Назначен"],
        },
        {
            "key": "predictions",
            "title": "ПРОГНОЗЫ",
        },
        {
            "key": "dicom",
            "title": "DICOM-ИССЛЕДОВАНИЯ",
        },
        {
            "key": "conclusion",
            "title": "ЗАКЛЮЧЕНИЕ И РЕКОМЕНДАЦИИ",
        },
    ],
    "signature": {
        "doctor_label": "Лечащий врач",
        "date_label": "Дата",
    },
}

TEMPLATE_LAB_REPORT = {
    "title": "ЛАБОРАТОРНЫЙ ОТЧЁТ",
    "table_headers": ["Показатель", "Значение", "Референсные значения", "Статус"],
    "sections": [
        {"key": "patient", "title": "ПАЦИЕНТ"},
        {"key": "lab", "title": "РЕЗУЛЬТАТЫ АНАЛИЗОВ"},
        {"key": "notes", "title": "ПРИМЕЧАНИЯ"},
    ],
}

TEMPLATE_CLINICAL_SUMMARY = {
    "title": "КЛИНИЧЕСКАЯ ВЫПИСКА",
    "sections": [
        {"key": "patient", "title": "ПАЦИЕНТ"},
        {"key": "anamnesis", "title": "АНАМНЕЗ"},
        {"key": "diagnoses", "title": "ДИАГНОЗЫ"},
        {"key": "operations", "title": "ПЕРЕНЕСЁННЫЕ ОПЕРАЦИИ"},
        {"key": "imaging", "title": "ЗАКЛЮЧЕНИЯ ИНСТРУМЕНТАЛЬНЫХ ИССЛЕДОВАНИЙ"},
        {"key": "conclusion", "title": "ЗАКЛЮЧЕНИЕ"},
    ],
}

TEMPLATE_DICOM_REPORT = {
    "title": "ОТЧЁТ ПО DICOM-ИССЛЕДОВАНИЮ",
    "sections": [
        {"key": "study", "title": "ПАРАМЕТРЫ ИССЛЕДОВАНИЯ"},
        {"key": "findings", "title": "ОПИСАНИЕ"},
        {"key": "impression", "title": "ЗАКЛЮЧЕНИЕ"},
        {"key": "measurements", "title": "ИЗМЕРЕНИЯ"},
    ],
}

DEFAULT_PATIENT_CARD_SECTIONS = [
    "patient",
    "anamnesis",
    "diagnoses",
    "lab",
    "medications",
    "predictions",
    "dicom",
    "conclusion",
]

GENDER_LABELS = {
    "m": "Мужской",
    "f": "Женский",
    "M": "Мужской",
    "F": "Женский",
    "м": "Мужской",
    "ж": "Женский",
}
