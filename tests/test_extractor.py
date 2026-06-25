"""Unit tests for clinical entity extraction from discharge documents."""

from app.prompts.clinical_prompts import build_gpt_clinical_prompt
from app.services.extractor import consolidate_diagnosis_labels, extract_entities, labs_dict_to_list

PATIENT_DOCX_SNIPPET = """
Перенесенные заболевания: ОРВИ, Хр. пиелонефрит
Перенесенные гинекологические заболевания: эрозия шейки матки, хр. эндометрит.
Гистологическое описание микропрепаратов: Хронический эндометрит, умеренной степени выраженности, неактивный.
Диагноз: N46, Бесплодие 2, мужской фактор. Рекомендован перенос криоэмбрионов.
Телефон: 339-390. Назначено: Амоксициллин, Эналаприл.
"""

CLINICAL_EXAM_SNIPPET = """
Перенесенные операции:
Лапароскопия в 2012г. №42317-19
Эндометриоидная гиперотомия. Маточные трубы проходимы.
Биопсия эндометрия: аспират из полости матки 13.11.2014 год.

Данные обследования
Инфекция	23.10.2018	23.10.2018
	ИФА	РПГА	Реакция микрометод Вассермана
ВИЧ	отр.
Сифилис	отр.	отр.	отр.
Гепатит В	отр.
Гепатит С	отр.
Клинический анализ крови – 20.10.2018
Показатель	значение	норма, единицы измерения
Гемоглобин	101 g/L	115-164 g/L
СОЭ	16 мм/час	2-15мм/час
Общий анализ мочи – 20.10.2018г
С/жёлтая, прозрачная. Лейкоциты 0-1, эритроциты 7-12.
Биохимический анализ крови – 20.10.2018.
Показатель	значение	норма, единицы измерения
глюкоза	4,6	4,2-6,4 мкмоль/л
Гормональное обследование: 20.10.2018г
Гормоны	показатели 	норма, единицы измерения
пролактин	142	95-729 ММЕ/мл
ПЦР анализ на ЗППП:  23.10.2018г
Инфекция	результат
Chlamydia trachomatis	не обнаружена
УЗИ органов малого таза: на 2 день цикла, дата исследования: 06.02.2018г.
Заключение: снижен овариальный резерв.
УЗИ молочных желез – 20.10.2018год.
 Заключение: Эхопатологии не выявлено.
Мазок на онкоцитологию – 20.10.2018г. – без особенностей.
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


def test_extract_operations():
    result = extract_entities(CLINICAL_EXAM_SNIPPET)
    ops = " ".join(result["operations"]).casefold()
    assert "лапароскопия" in ops
    assert "гиперотомия" in ops
    assert "биопсия эндометрия" in ops


def test_extract_lab_results_with_abnormal_flags():
    result = extract_entities(CLINICAL_EXAM_SNIPPET)
    labs = result["lab_results"]
    assert "гемоглобин" in labs
    assert labs["гемоглобин"]["abnormal"] is True
    assert labs["гемоглобин"]["value"] == "101 g/L"
    assert "соэ" in labs
    assert labs["соэ"]["abnormal"] is True
    assert labs["chlamydia trachomatis"]["abnormal"] is False
    assert "общий анализ мочи" in labs


def test_extract_imaging_conclusions():
    result = extract_entities(CLINICAL_EXAM_SNIPPET)
    imaging = " ".join(result["imaging_conclusions"]).casefold()
    assert "снижен овариальный резерв" in imaging
    assert "эхопатологии не выявлено" in imaging


def test_labs_dict_to_list():
    labs = {"гемоглобин": {"value": "101 g/L", "reference": "115-164 g/L", "abnormal": True}}
    rows = labs_dict_to_list(labs)
    assert rows[0]["name"] == "гемоглобин"
    assert rows[0]["value"] == "101 g/L"


def test_clinical_prompt_includes_labs_and_operations():
    features = {
        "name": "Иванова А.",
        "age": 32,
        "gender": "женский",
        "diagnoses": ["N46 (Бесплодие 2, мужской фактор)"],
        "anamnesis": ["хр. эндометрит"],
        "operations": ["Лапароскопия в 2012г."],
        "medications": [],
        "lab_results": {"гемоглобин": {"value": "101 g/L", "reference": "115-164", "abnormal": True}},
        "imaging_conclusions": ["снижен овариальный резерв"],
    }
    prompt = build_gpt_clinical_prompt(features)
    assert "гемоглобин" in prompt
    assert "ОТКЛОНЕНИЕ" in prompt
    assert "Лапароскопия" in prompt
    assert "овариальный резерв" in prompt
