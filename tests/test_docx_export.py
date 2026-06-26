"""Tests for DOCX export HTTP helpers."""

from app.routes.docx_export import _ascii_filename_fallback, _attachment_disposition


def test_attachment_disposition_latin1_safe_with_cyrillic():
    filename = "patient_card_10_Иванов_Иван_20250624.docx"
    header = _attachment_disposition(filename)
    header.encode("latin-1")
    assert 'filename="patient_card_10' in header
    assert "filename*=UTF-8''" in header
    assert "%D0%98" in header


def test_ascii_filename_fallback_strips_cyrillic():
    assert _ascii_filename_fallback("patient_card_10_Иванов_Иван.docx") == "patient_card_10_.docx"
