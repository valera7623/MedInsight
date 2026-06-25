"""Unit tests for dashboard diagnosis aggregation."""

from app.services.extractor import diagnoses_from_parsed_data, medications_from_parsed_data


def test_dashboard_uses_full_text_when_stored_diagnoses_filtered():
    parsed = {
        "diagnoses": ["противопоказаний к вынашиванию беременности нет"],
        "full_text": "Диагноз: N97.0, Бесплодие женское.\nГемоглобин 120 g/L",
        "medications": ["Гемоглобин"],
        "lab_results": {"гемоглобин": {"value": "120 g/L"}},
    }
    assert diagnoses_from_parsed_data(parsed) == ["N97.0 (Бесплодие женское)"]
    assert medications_from_parsed_data(parsed) == []
