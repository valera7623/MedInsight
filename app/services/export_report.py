"""Helpers for patient PDF export content."""

from __future__ import annotations

import re
from pathlib import Path

from app.models import Document
from app.services.extractor import diagnoses_from_parsed_data, medications_from_parsed_data
from app.services.parser import format_discharge_text_for_display

MAX_DISCHARGE_CHARS = 30_000
_GENERATED_REPORT_NAME = re.compile(r"^patient_\d+_report\.pdf$", re.IGNORECASE)
_MEDINSIGHT_REPORT_MARKERS = (
    "MedInsight — Отчёт по пациенту",
    "MedInsight — Отчет по пациенту",
    "MedInsight - Отчёт по пациенту",
)


def is_generated_report_document(doc: Document) -> bool:
    filename = (doc.filename or "").lower()
    if _GENERATED_REPORT_NAME.match(filename):
        return True
    text = (doc.parsed_data or {}).get("full_text") or ""
    return any(marker in text for marker in _MEDINSIGHT_REPORT_MARKERS)


def _document_sort_key(doc: Document) -> tuple[int, str]:
    if is_generated_report_document(doc):
        return (9, doc.filename or "")
    ext = Path(doc.filename or "").suffix.lower()
    priority = {".docx": 0, ".doc": 1, ".pdf": 2}.get(ext, 3)
    return (priority, doc.filename or "")


def collect_patient_export_clinical_data(documents: list[Document]) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """Return diagnoses, medications and formatted discharge blocks for export."""
    diagnoses: set[str] = set()
    medications: set[str] = set()
    discharge_blocks: list[tuple[str, str]] = []
    seen_fingerprints: set[str] = set()

    for doc in sorted(documents, key=_document_sort_key):
        if is_generated_report_document(doc) or not doc.parsed_data:
            continue

        diagnoses.update(diagnoses_from_parsed_data(doc.parsed_data))
        medications.update(medications_from_parsed_data(doc.parsed_data))

        raw_text = doc.parsed_data.get("full_text") or ""
        if not raw_text.strip():
            continue

        formatted = format_discharge_text_for_display(raw_text)
        fingerprint = re.sub(r"\s+", " ", formatted[:800]).casefold()
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        discharge_blocks.append((doc.filename, formatted))

    return sorted(diagnoses), sorted(medications, key=str.casefold), discharge_blocks
