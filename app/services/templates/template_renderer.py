"""Jinja2 template rendering and PDF generation."""

from __future__ import annotations

import logging
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateNotFound, select_autoescape
from sqlalchemy.orm import Session

from app.models import ReportTemplate
from app.services.pdf_generator import PdfGenerator

logger = logging.getLogger(__name__)

_BASE_CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: Helvetica, 'DejaVu Sans', sans-serif; font-size: 12px; color: #1e293b; }
.header { text-align: center; border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 20px; }
.header h1 { color: #2563eb; margin: 0; }
.section { margin: 18px 0; page-break-inside: avoid; }
.section h2 { color: #1e293b; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
.row { margin: 6px 0; }
.label { font-weight: bold; display: inline-block; width: 180px; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
th, td { border: 1px solid #e2e8f0; padding: 6px 8px; text-align: left; }
th { background-color: #f1f5f9; }
.footer { text-align: center; font-size: 10px; color: #94a3b8; margin-top: 40px; }
img { max-width: 100%; height: auto; margin: 8px 0; }
"""


class _DbTemplateLoader(BaseLoader):
    def __init__(self, html: str, css: str | None) -> None:
        self.html = html
        self.css = css or _BASE_CSS

    def get_source(self, environment, template):  # noqa: ANN001
        if template == "report.html":
            return self.html, None, lambda: True
        if template == "report.css":
            return self.css, None, lambda: True
        raise TemplateNotFound(template)


class TemplateRenderer:
    """Render report templates to HTML and PDF."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.pdf = PdfGenerator()

    def _get_template(self, template_id: int) -> ReportTemplate:
        row = self.db.get(ReportTemplate, template_id)
        if not row:
            raise ValueError(f"Template {template_id} not found")
        return row

    def get_template_variables(self, template_id: int) -> list[dict]:
        row = self._get_template(template_id)
        return [
            {
                "variable_name": v.variable_name,
                "variable_type": v.variable_type,
                "variable_description": v.variable_description,
                "is_required": v.is_required,
                "default_value": v.default_value,
            }
            for v in row.variables
        ]

    def validate_template_data(self, template_id: int, data: dict) -> bool:
        variables = self.get_template_variables(template_id)
        for var in variables:
            if var["is_required"] and var["variable_name"] not in data:
                nested = var["variable_name"] in ("patient", "dicom_study")
                if not nested:
                    return False
        return True

    def render_template(self, template_id: int, data: dict) -> str:
        row = self._get_template(template_id)
        env = Environment(
            loader=_DbTemplateLoader(row.template_html, row.template_css),
            autoescape=select_autoescape(["html", "xml"]),
        )
        body = env.get_template("report.html").render(**data)
        if "<html" not in body.lower():
            css = row.template_css or _BASE_CSS
            body = f"<!DOCTYPE html><html><head><meta charset='UTF-8'><style>{css}</style></head><body>{body}</body></html>"
        return body

    def preview_template(self, template_id: int, data: dict) -> str:
        return self.render_template(template_id, data)

    def render_to_pdf(self, template_id: int, data: dict, *, watermark: str | None = None) -> bytes:
        html = self.render_template(template_id, data)
        pdf = self.pdf.html_to_pdf(html)
        footer = f"MedInsight | {data.get('generated_at', '')}"
        pdf = self.pdf.add_header_footer(pdf, data.get("header", "MedInsight Clinical Report"), footer)
        if watermark:
            pdf = self.pdf.add_watermark(pdf, watermark)
        return pdf
