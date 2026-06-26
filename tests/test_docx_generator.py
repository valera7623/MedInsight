"""Unit tests for DOCX patient card generation."""

from io import BytesIO
from zipfile import ZipFile

from app.services.docx_generator import DocxGenerator


def test_build_patient_card_bytes_creates_valid_docx():
    buffer = DocxGenerator.build_patient_card_bytes(
        patient_data={
            "full_name": "Иванова Анна",
            "birth_date": "01.01.1990",
            "gender": "Женский",
            "gender_raw": "f",
            "phone": "+7999",
            "email": "a@example.com",
            "department": "Терапия",
        },
        lab_results=[{"name": "Гемоглобин", "value": "120", "reference": "115-150", "status": "норма"}],
        diagnoses=[{"code": "J06", "name": "ОРВИ", "type": "основной"}],
        medications=[{"name": "Парацетамол", "dosage": "500 мг", "frequency": "по необходимости", "prescribed_date": "—"}],
        predictions=[{"type": "Риск реадмиссии", "risk": 10, "factors": []}],
        dicom_studies=[],
        anamnesis=["ОРВИ в анамнезе"],
        sections=["patient", "diagnoses", "lab", "conclusion"],
        watermark="TEST",
    )
    assert isinstance(buffer, BytesIO)
    data = buffer.getvalue()
    assert data[:2] == b"PK"
    with ZipFile(BytesIO(data)) as archive:
        assert "word/document.xml" in archive.namelist()


def test_generate_demo_diagnoses_has_primary():
    diagnoses = DocxGenerator.generate_demo_diagnoses()
    assert 1 <= len(diagnoses) <= 3
    assert diagnoses[0]["type"] == "основной"


def test_generate_random_lab_results_covers_categories():
    results = DocxGenerator.generate_random_lab_results("male")
    categories = {item["category"] for item in results}
    assert "Общий анализ крови" in categories
    assert "Биохимический анализ крови" in categories
    assert "Общий анализ мочи" in categories
    assert all(item.get("status") in {"норма", "повышено", "понижено"} for item in results)


def test_build_patient_card_uses_demo_when_lab_and_diagnoses_empty():
    buffer = DocxGenerator.build_patient_card_bytes(
        patient_data={
            "full_name": "Тест Тест",
            "birth_date": "01.01.1980",
            "gender": "Мужской",
            "gender_raw": "m",
            "phone": "—",
            "email": "—",
            "department": "—",
        },
        lab_results=[],
        diagnoses=[],
        medications=[],
        predictions=[],
        dicom_studies=[],
        sections=["patient", "diagnoses", "lab", "conclusion"],
    )
    xml = ZipFile(BytesIO(buffer.getvalue())).read("word/document.xml").decode("utf-8")
    assert "ДИАГНОЗЫ" in xml
    assert "ЛАБОРАТОРНЫЕ АНАЛИЗЫ" in xml
    assert "Гемоглобин" in xml or "Глюкоза" in xml
