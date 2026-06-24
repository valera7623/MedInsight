"""HTML → PDF conversion and PDF post-processing (ReportLab / xhtml2pdf)."""

from __future__ import annotations

import io
import logging
from typing import Any

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdf_canvas

logger = logging.getLogger(__name__)


class PdfGenerator:
    """Convert rendered HTML to PDF and apply post-processing."""

    @staticmethod
    def html_to_pdf(html: str) -> bytes:
        from xhtml2pdf import pisa

        buffer = io.BytesIO()
        result = pisa.CreatePDF(io.StringIO(html), dest=buffer, encoding="utf-8")
        if result.err:
            raise RuntimeError(f"PDF generation failed (xhtml2pdf errors: {result.err})")
        return buffer.getvalue()

    @staticmethod
    def add_header_footer(pdf: bytes, header: str, footer: str) -> bytes:
        reader = PdfReader(io.BytesIO(pdf))
        writer = PdfWriter()
        for page in reader.pages:
            packet = io.BytesIO()
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            c = pdf_canvas.Canvas(packet, pagesize=(width, height))
            c.setFont("Helvetica", 9)
            if header:
                c.drawString(40, height - 30, header[:120])
            if footer:
                c.drawString(40, 20, footer[:120])
            c.save()
            overlay = PdfReader(packet).pages[0]
            page.merge_page(overlay)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    @staticmethod
    def add_watermark(pdf: bytes, text: str) -> bytes:
        reader = PdfReader(io.BytesIO(pdf))
        writer = PdfWriter()
        for page in reader.pages:
            packet = io.BytesIO()
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            c = pdf_canvas.Canvas(packet, pagesize=(width, height))
            c.saveState()
            c.setFont("Helvetica", 40)
            c.setFillGray(0.85, 0.3)
            c.translate(width / 2, height / 2)
            c.rotate(45)
            c.drawCentredString(0, 0, text[:40])
            c.restoreState()
            c.save()
            overlay = PdfReader(packet).pages[0]
            page.merge_page(overlay)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    @staticmethod
    def merge_pdfs(pdfs: list[bytes]) -> bytes:
        writer = PdfWriter()
        for data in pdfs:
            reader = PdfReader(io.BytesIO(data))
            for page in reader.pages:
                writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    @staticmethod
    def get_pdf_metadata(pdf: bytes) -> dict[str, Any]:
        reader = PdfReader(io.BytesIO(pdf))
        meta = reader.metadata or {}
        return {
            "pages": len(reader.pages),
            "title": meta.get("/Title"),
            "author": meta.get("/Author"),
            "creator": meta.get("/Creator"),
            "size_bytes": len(pdf),
        }
