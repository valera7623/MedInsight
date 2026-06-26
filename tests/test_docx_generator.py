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
            "phone": "+7999",
            "email": "a@example.com",
            "department": "Терапия",
        },
        lab_results=[{"name": "Гемоглобин", "value": "120", "reference": "115-150", "status": "норма"}],
        diagnoses=[{"code": "J06", "name": "ОРВИ"}],
        medications=[{"name": "Парацетамол", "dosage": "500 мг", "frequency": "по необходимости", "prescribed_date": "—"}],
        predictions=[{"type": "Риск реадмиссии", "risk": 10, "factors": []}],
        dicom_studies=[],
        anamnesis=["ОРВИ в анамнезе"],
        sections=["patient", "diagnoses", "lab"],
        watermark="TEST",
    )
    assert isinstance(buffer, BytesIO)
    data = buffer.getvalue()
    assert data[:2] == b"PK"
    with ZipFile(BytesIO(data)) as archive:
        assert "word/document.xml" in archive.namelist()
