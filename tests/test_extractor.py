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
    assert diagnoses == ["N46 (Бесплодие 2, мужской фактор)"]
    assert "ОРВИ" not in diagnoses


def test_anamnesis_vitae_separate_from_diagnoses():
    result = extract_entities(PATIENT_DOCX_SNIPPET)
    anamnesis = {a.casefold() for a in result["anamnesis"]}
    diagnoses = {d.casefold() for d in result["diagnoses"]}
    assert "орви" in anamnesis
    assert "хр. пиелонефрит" in anamnesis
    assert "эрозия шейки матки" in anamnesis
    assert "хр. эндометрит" in anamnesis
    assert "хронический эндометрит" in anamnesis
    assert "орви" not in diagnoses
    assert "хр. пиелонефрит" not in diagnoses


def test_consolidate_legacy_drops_anamnesis_from_diagnoses():
    legacy = ["N46", "Бесплодие 2", "мужской фактор", "ОРВИ", "Хр. пиелонефрит"]
    merged = consolidate_diagnosis_labels(legacy)
    assert merged == ["N46 (Бесплодие 2, мужской фактор)"]
