"""CRUD operations for report templates."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ReportTemplate, ReportTemplateVariable

logger = logging.getLogger(__name__)

DEFAULT_VARIABLES: dict[str, list[dict]] = {
    "clinical": [
        {"variable_name": "patient", "variable_type": "table", "is_required": True, "variable_description": "Patient data"},
        {"variable_name": "diagnoses", "variable_type": "table", "is_required": False},
        {"variable_name": "medications", "variable_type": "table", "is_required": False},
        {"variable_name": "lab_results", "variable_type": "table", "is_required": False},
        {"variable_name": "predictions", "variable_type": "table", "is_required": False},
    ],
    "laboratory": [
        {"variable_name": "patient", "variable_type": "table", "is_required": True},
        {"variable_name": "lab_results", "variable_type": "table", "is_required": True},
    ],
    "dicom": [
        {"variable_name": "patient", "variable_type": "table", "is_required": True},
        {"variable_name": "dicom_study", "variable_type": "table", "is_required": True},
        {"variable_name": "findings", "variable_type": "table", "is_required": False},
        {"variable_name": "images", "variable_type": "image", "is_required": False},
    ],
    "prediction": [
        {"variable_name": "patient", "variable_type": "table", "is_required": True},
        {"variable_name": "predictions", "variable_type": "table", "is_required": True},
    ],
    "full": [
        {"variable_name": "patient", "variable_type": "table", "is_required": True},
        {"variable_name": "diagnoses", "variable_type": "table", "is_required": False},
        {"variable_name": "lab_results", "variable_type": "table", "is_required": False},
        {"variable_name": "predictions", "variable_type": "table", "is_required": False},
        {"variable_name": "dicom_study", "variable_type": "table", "is_required": False},
    ],
}


class TemplateManager:
    """Manage report template lifecycle."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.templates_dir = Path(settings.REPORTS_TEMPLATES_DIR)

    def _load_file_template(self, template_type: str) -> tuple[str, str | None]:
        path = self.templates_dir / f"{template_type}.jinja2"
        if not path.exists():
            return "<html><body><h1>{{ title | default('Report') }}</h1><pre>{{ patient }}</pre></body></html>", None
        content = path.read_text(encoding="utf-8")
        return content, None

    def _attach_variables(self, template: ReportTemplate, template_type: str) -> None:
        for var in DEFAULT_VARIABLES.get(template_type, []):
            self.db.add(ReportTemplateVariable(template_id=template.id, **var))

    def create_template(self, data: dict) -> ReportTemplate:
        template_type = data["template_type"]
        html = data.get("template_html")
        if not html:
            html, css = self._load_file_template(template_type)
            data.setdefault("template_css", css)
        else:
            css = data.get("template_css")

        row = ReportTemplate(
            tenant_id=data["tenant_id"],
            name=data["name"],
            description=data.get("description"),
            template_type=template_type,
            template_html=html,
            template_css=css,
            is_active=data.get("is_active", True),
            created_by=data["created_by"],
        )
        self.db.add(row)
        self.db.flush()
        for var in data.get("variables") or DEFAULT_VARIABLES.get(template_type, []):
            self.db.add(ReportTemplateVariable(template_id=row.id, **var))
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_template(self, template_id: int) -> ReportTemplate | None:
        return self.db.get(ReportTemplate, template_id)

    def list_templates(self, tenant_id: int, *, active_only: bool = True) -> list[ReportTemplate]:
        query = self.db.query(ReportTemplate).filter(ReportTemplate.tenant_id == tenant_id)
        if active_only:
            query = query.filter(ReportTemplate.is_active.is_(True))
        return query.order_by(ReportTemplate.name.asc()).all()

    def update_template(self, template_id: int, data: dict) -> ReportTemplate:
        row = self.get_template(template_id)
        if not row:
            raise ValueError(f"Template {template_id} not found")
        for key in ("name", "description", "template_type", "template_html", "template_css", "is_active"):
            if key in data and data[key] is not None:
                setattr(row, key, data[key])
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_template(self, template_id: int) -> bool:
        row = self.get_template(template_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def duplicate_template(self, template_id: int, new_name: str, created_by: int) -> ReportTemplate:
        source = self.get_template(template_id)
        if not source:
            raise ValueError(f"Template {template_id} not found")
        clone = ReportTemplate(
            tenant_id=source.tenant_id,
            name=new_name,
            description=source.description,
            template_type=source.template_type,
            template_html=source.template_html,
            template_css=source.template_css,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(clone)
        self.db.flush()
        for var in source.variables:
            self.db.add(
                ReportTemplateVariable(
                    template_id=clone.id,
                    variable_name=var.variable_name,
                    variable_type=var.variable_type,
                    variable_description=var.variable_description,
                    is_required=var.is_required,
                    default_value=var.default_value,
                )
            )
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def seed_defaults(self, tenant_id: int, created_by: int) -> list[ReportTemplate]:
        existing = self.list_templates(tenant_id, active_only=False)
        if existing:
            return existing
        names = {
            "clinical": "Клиническая выписка",
            "laboratory": "Результаты анализов",
            "dicom": "DICOM-отчёт",
            "prediction": "Прогноз рисков",
            "full": "Полный клинический обзор",
        }
        created = []
        for ttype, tname in names.items():
            html, css = self._load_file_template(ttype)
            row = self.create_template(
                {
                    "tenant_id": tenant_id,
                    "name": tname,
                    "template_type": ttype,
                    "template_html": html,
                    "template_css": css,
                    "created_by": created_by,
                }
            )
            created.append(row)
        logger.info("Seeded %d default report templates for tenant %s", len(created), tenant_id)
        return created
