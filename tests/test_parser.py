"""Unit tests for document text extraction."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.parser import (
    SUPPORTED_EXTENSIONS,
    extract_text_from_doc,
    parse_document,
)


def test_supported_extensions_include_doc():
    assert ".doc" in SUPPORTED_EXTENSIONS
    assert ".docx" in SUPPORTED_EXTENSIONS
    assert ".pdf" in SUPPORTED_EXTENSIONS


def test_extract_text_from_doc_uses_antiword(tmp_path: Path):
    doc_path = tmp_path / "discharge.doc"
    doc_path.write_bytes(b"fake-doc-bytes")

    with patch("app.services.parser.shutil.which", side_effect=lambda name: "/usr/bin/antiword" if name == "antiword" else None), patch(
        "app.services.parser._run_text_extractor",
        return_value="Диагноз: N46",
    ) as run_extractor:
        text = extract_text_from_doc(doc_path)

    assert text == "Диагноз: N46"
    run_extractor.assert_called_once()
    assert run_extractor.call_args.args[0] == ["/usr/bin/antiword", "-m", "UTF-8.txt", str(doc_path)]


def test_extract_text_from_doc_falls_back_to_catdoc(tmp_path: Path):
    doc_path = tmp_path / "discharge.doc"
    doc_path.write_bytes(b"fake-doc-bytes")

    def which(name: str):
        if name == "antiword":
            return None
        if name == "catdoc":
            return "/usr/bin/catdoc"
        return None

    with patch("app.services.parser.shutil.which", side_effect=which), patch(
        "app.services.parser._run_text_extractor",
        return_value="Текст выписки",
    ) as run_extractor:
        text = extract_text_from_doc(doc_path)

    assert text == "Текст выписки"
    run_extractor.assert_called_once_with(
        ["/usr/bin/catdoc", "-d", "utf-8", str(doc_path)],
        tool_name="catdoc",
    )


def test_extract_text_from_doc_raises_without_tools(tmp_path: Path):
    doc_path = tmp_path / "discharge.doc"
    doc_path.write_bytes(b"fake-doc-bytes")

    with patch("app.services.parser.shutil.which", return_value=None):
        with pytest.raises(ValueError, match="antiword"):
            extract_text_from_doc(doc_path)


def test_parse_document_routes_doc_suffix(tmp_path: Path):
    doc_path = tmp_path / "note.doc"
    doc_path.write_bytes(b"fake-doc-bytes")

    with patch("app.services.parser.extract_text_from_doc", return_value="  Текст  \nвыписки  ") as extract_doc:
        text = parse_document(str(doc_path))

    extract_doc.assert_called_once()
    assert text == "Текст выписки"
