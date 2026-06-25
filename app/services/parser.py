import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document as DocxDocument
from PyPDF2 import PdfReader

from app.utils.tracing import trace_span

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".doc", ".docx", ".pdf"}
SUPPORTED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.ms-word",
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


def _run_text_extractor(command: list[str], *, tool_name: str) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("%s failed for %s: %s", tool_name, command[-1], exc)
        return None

    if result.returncode != 0:
        logger.warning(
            "%s exit code %s for %s: %s",
            tool_name,
            result.returncode,
            command[-1],
            (result.stderr or result.stdout or "").strip(),
        )
        return None

    text = (result.stdout or "").strip()
    return text or None


def extract_text_from_doc(file_path: Path) -> str:
    """Extract plain text from legacy Microsoft Word .doc (OLE) files."""
    path = str(file_path)
    antiword = shutil.which("antiword")
    if antiword:
        text = _run_text_extractor([antiword, "-m", "UTF-8.txt", path], tool_name="antiword")
        if text:
            return text

    catdoc = shutil.which("catdoc")
    if catdoc:
        text = _run_text_extractor([catdoc, "-d", "utf-8", path], tool_name="catdoc")
        if text:
            return text

    raise ValueError(
        "Не удалось извлечь текст из DOC. Установите antiword (apt install antiword) "
        "или catdoc (apt install catdoc) на сервере."
    )


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
    elif suffix == ".doc":
        text = extract_text_from_doc(path)
    elif suffix == ".pdf":
        text = extract_text_from_pdf(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    text = re.sub(r"\s+", " ", text).strip()
    logger.info("Parsed %s: %d characters", path.name, len(text))
    return text
