"""Report template CRUD API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import ReportTemplate, User
from app.services.access import effective_tenant_id, require_tenant_access
from app.services.templates.template_manager import TemplateManager

router = APIRouter(prefix="/templates", tags=["report-templates"])


class TemplateVariableIn(BaseModel):
    variable_name: str
    variable_type: str = "text"
    variable_description: str | None = None
    is_required: bool = False
    default_value: str | None = None


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    template_type: str = Field(pattern=r"^(clinical|laboratory|dicom|prediction|full)$")
    template_html: str | None = None
    template_css: str | None = None
    is_active: bool = True
    variables: list[TemplateVariableIn] | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    template_type: str | None = Field(default=None, pattern=r"^(clinical|laboratory|dicom|prediction|full)$")
    template_html: str | None = None
    template_css: str | None = None
    is_active: bool | None = None


class DuplicateRequest(BaseModel):
    new_name: str = Field(min_length=1, max_length=255)


def _serialize(t: ReportTemplate) -> dict:
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "name": t.name,
        "description": t.description,
        "template_type": t.template_type,
        "is_active": t.is_active,
        "created_by": t.created_by,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "variables": [
            {
                "id": v.id,
                "variable_name": v.variable_name,
                "variable_type": v.variable_type,
                "variable_description": v.variable_description,
                "is_required": v.is_required,
                "default_value": v.default_value,
            }
            for v in t.variables
        ],
    }


@router.get("")
def list_templates(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant required")
    mgr = TemplateManager(db)
    mgr.seed_defaults(tenant_id, current_user.id)
    rows = mgr.list_templates(tenant_id)
    return [_serialize(t) for t in rows]


@router.get("/{template_id}")
def get_template(
    template_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    row = db.get(ReportTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    require_tenant_access(current_user, row.tenant_id)
    return _serialize(row)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant required")
    mgr = TemplateManager(db)
    row = mgr.create_template(
        {
            **body.model_dump(),
            "tenant_id": tenant_id,
            "created_by": current_user.id,
            "variables": [v.model_dump() for v in body.variables] if body.variables else None,
        }
    )
    return _serialize(row)


@router.put("/{template_id}")
def update_template(
    template_id: int,
    body: TemplateUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    row = db.get(ReportTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    require_tenant_access(current_user, row.tenant_id)
    mgr = TemplateManager(db)
    try:
        updated = mgr.update_template(template_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(updated)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    row = db.get(ReportTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    require_tenant_access(current_user, row.tenant_id)
    TemplateManager(db).delete_template(template_id)


@router.post("/{template_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_template(
    template_id: int,
    body: DuplicateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    row = db.get(ReportTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    require_tenant_access(current_user, row.tenant_id)
    mgr = TemplateManager(db)
    try:
        clone = mgr.duplicate_template(template_id, body.new_name, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(clone)
