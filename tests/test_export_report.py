"""Tests for patient PDF export content helpers."""

from app.models import Document
from app.services.export_report import collect_patient_export_clinical_data, is_generated_report_document


def _doc(filename: str, parsed_data: dict) -> Document:
    return Document(
        tenant_id=1,
        patient_id=1,
        user_id=1,
        filename=filename,
        file_path=f"/tmp/{filename}",
        file_size=100,
        mime_type="application/octet-stream",
        document_type="discharge",
        parsed_data=parsed_data,
    )


def test_skip_generated_report_pdf():
    doc = _doc(
        "patient_7_report.pdf",
        {"full_text": "MedInsight — Отчёт по пациенту\nФИО Сидоров", "diagnoses": ["N46"]},
    )
    assert is_generated_report_document(doc) is True


def test_collect_export_data_dedupes_doc_and_docx():
    text = (
        "Диагноз: N46, Бесплодие 2, мужской фактор. "
        "Перенесенные заболевания: ОРВИ. "
        "Клинический анализ крови – 20.10.2018"
    )
    parsed = {
        "diagnoses": ["N46", "Бесплодие 2", "мужской фактор"],
        "medications": ["Гемоглобин", "Амоксициллин"],
        "lab_results": {"гемоглобин": {"value": "101"}},
        "full_text": text,
    }
    docs = [
        _doc("patient.doc", parsed),
        _doc("patient (1).docx", parsed),
        _doc("patient_7_report.pdf", {"full_text": "MedInsight — Отчёт по пациенту", "diagnoses": ["N46"]}),
    ]
    diagnoses, medications, blocks = collect_patient_export_clinical_data(docs)
    assert diagnoses == ["N46 (Бесплодие 2, мужской фактор)"]
    assert medications == ["Амоксициллин"]
    assert len(blocks) == 1
    assert "Перенесенные заболевания" in blocks[0][1] or "\n" in blocks[0][1]
