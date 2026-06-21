import logging
import re
import tempfile
from pathlib import Path

from docx import Document as DocxDocument
from PyPDF2 import PdfReader

from app.utils.tracing import trace_span

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".docx", ".pdf"}
SUPPORTED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def extract_text_from_docx(file_path: Path) -> str:
    doc = DocxDocument(str(file_path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text_from_pdf(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n".join(pages)


def parse_document_from_bytes(content: bytes, filename: str) -> str:
    """Parse document from in-memory bytes (for encrypted files)."""
    suffix = Path(filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        return parse_document(tmp.name)


@trace_span("parser_agent", {"agent": "parser"})
def parse_document(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".docx":
        text = extract_text_from_docx(path)
    elif suffix == ".pdf":
        text = extract_text_from_pdf(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    text = re.sub(r"\s+", " ", text).strip()
    logger.info("Parsed %s: %d characters", path.name, len(text))
    return text
