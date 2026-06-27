import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
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

# Common discharge section headers — insert line breaks when Word stores text as one block.
DISCHARGE_SECTION_MARKERS = [
    "Перенесенные гинекологические заболевания",
    "Перенесенные заболевания",
    "Перенесенные операции",
    "Гистологическое описание микропрепаратов",
    "Гистероскопия",
    "Данные обследования",
    "Клинический анализ крови",
    "Общий анализ мочи",
    "Биохимический анализ крови",
    "Коагулограмма",
    "Гормональное обследование",
    "ПЦР анализ",
    "Исследование сыворотки крови",
    "Мазок на онкоцитологию",
    "Мазок на флору",
    "УЗИ органов малого таза",
    "УЗИ молочных желез",
    "УЗИ щитовидной железы",
    "Консультация терапевта",
    "Диагноз:",
    "Рекомендован",
    "ЭКГ:",
    "ФЛГ",
]


def _normalize_extracted_text(text: str) -> str:
    """Keep line breaks for readability; collapse only horizontal whitespace."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        lines.append(line)

    result: list[str] = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                result.append("")
            prev_empty = True
            continue
        result.append(line)
        prev_empty = False
    return "\n".join(result).strip()


def _structure_discharge_text(text: str) -> str:
    """Insert line breaks before known section headers in single-block discharge forms."""
    if text.count("\n") >= 8:
        return text
    structured = text
    for marker in DISCHARGE_SECTION_MARKERS:
        structured = re.sub(
            rf"(?<!\n)(?<=\S)\s+({re.escape(marker)})",
            r"\n\1",
            structured,
            flags=re.IGNORECASE,
        )
    return structured


def _clean_pipe_tables(text: str) -> str:
    """Convert antiword pipe-separated table rows to tab-separated lines."""
    lines_out: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if "|" in line:
            cells = [re.sub(r"\s+", " ", cell).strip() for cell in line.split("|")]
            cells = [cell for cell in cells if cell]
            if len(cells) >= 2:
                lines_out.append("\t".join(cells))
                continue
        if line:
            lines_out.append(line)
    return "\n".join(lines_out)


def format_discharge_text_for_display(text: str) -> str:
    """Normalize legacy and freshly parsed discharge text for UI/PDF display."""
    if not text:
        return ""
    cleaned = _normalize_extracted_text(text)
    cleaned = _clean_pipe_tables(cleaned)
    return _structure_discharge_text(cleaned)


def _iter_docx_blocks(document: DocxDocument):
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def extract_text_from_docx(file_path: Path) -> str:
    doc = DocxDocument(str(file_path))
    blocks: list[str] = []
    for block in _iter_docx_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                blocks.append(text)
            continue

        for row in block.rows:
            cells = [re.sub(r"\s+", " ", cell.text).strip() for cell in row.cells]
            cells = [cell for cell in cells if cell]
            if cells:
                blocks.append("\t".join(cells))
    return "\n".join(blocks)


def extract_text_from_pdf(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n\n".join(pages)


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

    text = _normalize_extracted_text(text)
    text = _clean_pipe_tables(text)
    text = _structure_discharge_text(text)
    logger.info("Parsed %s: %d characters", path.name, len(text))
    return text
