"""Unit tests for clinical entity extraction from discharge documents."""

from app.services.extractor import extract_entities

PATIENT_DOCX_SNIPPET = """
Перенесенные заболевания: ОРВИ, Хр. пиелонефрит
Перенесенные гинекологические заболевания: эрозия шейки матки, хр. эндометрит.
Гистологическое описание микропрепаратов: Хронический эндометрит, умеренной степени выраженности, неактивный.
Диагноз: N46, Бесплодие 2, мужской фактор. Рекомендован перенос криоэмбрионов.
Телефон: 339-390. Назначено: Амоксициллин, Эналаприл.
"""


def test_patient_docx_false_medications_filtered():
    result = extract_entities(PATIENT_DOCX_SNIPPET)
    meds = {m.lower() for m in result["medications"]}
    assert "рекомендован" not in meds
    assert "телефон" not in meds
    assert "амоксициллин" in meds
    assert "эналаприл" in meds


def test_patient_docx_textual_diagnoses_from_anamnesis():
    result = extract_entities(PATIENT_DOCX_SNIPPET)
    diagnoses = {d.casefold() for d in result["diagnoses"]}
    assert "n46" in diagnoses
    assert "орви" in diagnoses
    assert "хр. пиелонефрит" in diagnoses
    assert "эрозия шейки матки" in diagnoses
    assert "хр. эндометрит" in diagnoses
    assert "хронический эндометрит" in diagnoses
    assert "бесплодие 2" in diagnoses
    assert "мужской фактор" in diagnoses
