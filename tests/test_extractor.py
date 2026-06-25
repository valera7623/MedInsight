"""Unit tests for clinical entity extraction from discharge documents."""

from app.services.extractor import consolidate_diagnosis_labels, extract_entities

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


def test_patient_docx_rejects_therapist_conclusion():
    text = """
    Консультация терапевта- Диагноз: Заключение: противопоказаний к вынашиванию беременности нет.
    Диагноз: N46, Бесплодие 2, мужской фактор.
    """ + PATIENT_DOCX_SNIPPET
    result = extract_entities(text)
    diagnoses = {d.casefold() for d in result["diagnoses"]}
    assert "противопоказаний к вынашиванию беременности нет" not in diagnoses
    assert "заключение" not in diagnoses


def test_icd_merged_with_descriptors():
    result = extract_entities(PATIENT_DOCX_SNIPPET)
    diagnoses = result["diagnoses"]
    assert "N46 (Бесплодие 2, мужской фактор)" in diagnoses
    assert "N46" not in diagnoses
    assert "Бесплодие 2" not in diagnoses
    assert "мужской фактор" not in diagnoses


def test_consolidate_legacy_split_icd_labels():
    legacy = ["N46", "Бесплодие 2", "мужской фактор", "ОРВИ"]
    merged = consolidate_diagnosis_labels(legacy)
    assert "N46 (Бесплодие 2, мужской фактор)" in merged
    assert "ОРВИ" in merged
    assert "N46" not in merged
    assert "Бесплодие 2" not in merged


def test_patient_docx_textual_diagnoses_from_anamnesis():
    result = extract_entities(PATIENT_DOCX_SNIPPET)
    diagnoses = {d.casefold() for d in result["diagnoses"]}
    assert "n46 (бесплодие 2, мужской фактор)" in diagnoses
    assert "орви" in diagnoses
    assert "хр. пиелонефрит" in diagnoses
    assert "эрозия шейки матки" in diagnoses
    assert "хр. эндометрит" in diagnoses
    assert "хронический эндометрит" in diagnoses
