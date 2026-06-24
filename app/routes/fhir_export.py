"""REST API for FHIR export (authenticated MedInsight users)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import User
from app.services.access import effective_tenant_id, require_tenant_access
from app.services.fhir.exporter import FhirExporter
from app.services.fhir.fhir_models import fhir_dump
from app.services.list_queries import patients_scope

router = APIRouter(prefix="/fhir/export", tags=["fhir-export"])


class FhirBatchExportRequest(BaseModel):
    from_date: datetime
    to_date: datetime
    resource_types: list[str] = Field(
        default_factory=lambda: ["Patient", "Observation", "DiagnosticReport", "ImagingStudy"]
    )
    tenant_id: int | None = None


def _require_fhir() -> None:
    if not settings.FHIR_ENABLED:
        raise HTTPException(status_code=503, detail="FHIR integration is disabled")


def _fhir_json(resource: Any) -> dict:
    return fhir_dump(resource)


@router.get("/patient/{patient_id}")
def export_patient_bundle(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    _require_fhir()
    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    if not patients_scope(db, current_user, tid).filter_by(id=patient_id).first():
        raise HTTPException(status_code=404, detail="Patient not found")
    exporter = FhirExporter(db)
    try:
        bundle = exporter.export_patient_bundle(patient_id)
        return _fhir_json(bundle)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tenant/{tenant_id}")
def export_tenant_patients(
    tenant_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
) -> dict:
    _require_fhir()
    require_tenant_access(current_user, tenant_id)
    exporter = FhirExporter(db)
    bundle = exporter.export_all_patients(tenant_id, user=current_user, request_tenant_id=tenant_id)
    return _fhir_json(bundle)


@router.get("/dicom/{study_uid}")
def export_dicom_study(
    study_uid: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    _require_fhir()
    exporter = FhirExporter(db)
    try:
        study = exporter.export_dicom_study(study_uid)
        return _fhir_json(study)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/batch")
def export_batch(
    body: FhirBatchExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    _require_fhir()
    tid = body.tenant_id or effective_tenant_id(current_user, get_request_tenant_id(request))
    if tid is not None:
        require_tenant_access(current_user, tid)
    exporter = FhirExporter(db)
    bundle = exporter.export_by_date(
        body.from_date,
        body.to_date,
        user=current_user,
        tenant_id=tid,
        resource_types=body.resource_types,
    )
    return _fhir_json(bundle)
