"""PDF report generation and download API."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import GeneratedReport, Patient, ReportTemplate, User
from app.services.access import can_export, effective_tenant_id, require_tenant_access
from app.services.templates.report_data import CONTEXT_BUILDERS
from app.services.templates.template_renderer import TemplateRenderer
from app.tasks.report_task import generate_report_from_template
from app.utils.pagination import PaginationParams, paginate

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    template_id: int
    patient_id: int
    data: dict[str, Any] | None = None
    study_uid: str | None = None
    watermark: str | None = None


class PreviewRequest(BaseModel):
    template_id: int
    patient_id: int | None = None
    data: dict[str, Any] | None = None
    study_uid: str | None = None


def _report_dump(r: GeneratedReport) -> dict:
    return {
        "id": r.id,
        "template_id": r.template_id,
        "patient_id": r.patient_id,
        "user_id": r.user_id,
        "status": r.status,
        "pdf_path": r.pdf_path,
        "created_at": r.created_at,
        "completed_at": r.completed_at,
        "error_message": r.error_message,
        "download_url": f"/api/reports/{r.id}/pdf" if r.status == "completed" else None,
    }


def _build_context(db: Session, template: ReportTemplate, patient_id: int, extra: dict | None, study_uid: str | None) -> dict:
    builder = CONTEXT_BUILDERS.get(template.template_type, CONTEXT_BUILDERS["clinical"])
    if template.template_type == "dicom":
        return builder(db, patient_id, study_uid=study_uid, extra=extra)
    return builder(db, patient_id, extra=extra)


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
def generate_report(
    body: GenerateReportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_export(current_user):
        raise HTTPException(status_code=403, detail="Cannot generate reports")

    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    template = db.get(ReportTemplate, body.template_id)
    if not template or not template.is_active:
        raise HTTPException(status_code=404, detail="Template not found")
    require_tenant_access(current_user, template.tenant_id)

    patient = db.get(Patient, body.patient_id)
    if not patient or patient.tenant_id != template.tenant_id:
        raise HTTPException(status_code=404, detail="Patient not found")

    context = _build_context(db, template, body.patient_id, body.data, body.study_uid)
    report = GeneratedReport(
        template_id=template.id,
        patient_id=body.patient_id,
        user_id=current_user.id,
        tenant_id=template.tenant_id,
        report_data=context,
        status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    payload = {
        "study_uid": body.study_uid,
        "watermark": settings.DEMO_WATERMARK if settings.DEMO_MODE else body.watermark,
    }
    task_result = generate_report_from_template(report.id, payload)

    return {
        "report_id": report.id,
        "status": "generating",
        "task_id": task_result if isinstance(task_result, str) else None,
        "download_url": f"/api/reports/{report.id}/pdf",
    }


@router.post("/preview")
def preview_report(
    body: PreviewRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    template = db.get(ReportTemplate, body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    require_tenant_access(current_user, template.tenant_id)

    if body.patient_id:
        context = _build_context(db, template, body.patient_id, body.data, body.study_uid)
    else:
        context = body.data or {"generated_at": datetime.utcnow().isoformat(), "patient": {"first_name": "Demo", "last_name": "Patient"}}

    renderer = TemplateRenderer(db)
    html = renderer.preview_template(template.id, context)
    return HTMLResponse(content=html)


@router.get("/{report_id}")
def get_report(
    report_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    report = db.get(GeneratedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    require_tenant_access(current_user, report.tenant_id)
    return _report_dump(report)


@router.get("/{report_id}/pdf")
def download_report_pdf(
    report_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    report = db.get(GeneratedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    require_tenant_access(current_user, report.tenant_id)
    if report.status != "completed" or not report.pdf_path:
        raise HTTPException(status_code=409, detail=f"Report status: {report.status}")
    path = Path(report.pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing")
    max_bytes = settings.REPORTS_MAX_FILE_SIZE_MB * 1024 * 1024
    if path.stat().st_size > max_bytes:
        raise HTTPException(status_code=413, detail="Report file too large")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("")
def list_reports(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    patient_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    query = db.query(GeneratedReport)
    if tenant_id is not None:
        query = query.filter(GeneratedReport.tenant_id == tenant_id)
    if patient_id is not None:
        query = query.filter(GeneratedReport.patient_id == patient_id)
    query = query.order_by(GeneratedReport.created_at.desc())
    params = PaginationParams(page=page, limit=limit)
    return paginate(query, params, model=GeneratedReport, allowed_sort=("id", "created_at"), serializer=_report_dump)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    report = db.get(GeneratedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    require_tenant_access(current_user, report.tenant_id)
    if report.pdf_path:
        Path(report.pdf_path).unlink(missing_ok=True)
    db.delete(report)
    db.commit()
