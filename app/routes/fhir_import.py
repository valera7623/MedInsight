"""REST API for FHIR import (authenticated MedInsight users)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fhir.resources.bundle import Bundle
from fhir.resources.patient import Patient
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import User
from app.services.access import effective_tenant_id
from app.services.fhir.importer import FhirImporter
from app.services.fhir.smart_on_fhir import SmartOnFhirClient

router = APIRouter(prefix="/fhir/import", tags=["fhir-import"])


class EhrImportRequest(BaseModel):
    ehr_patient_id: str = Field(min_length=1)
    authorization_url: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    fhir_base_url: str | None = None


def _require_fhir() -> None:
    if not settings.FHIR_ENABLED:
        raise HTTPException(status_code=503, detail="FHIR integration is disabled")


@router.post("/bundle")
def import_bundle(
    payload: dict[str, Any],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    _require_fhir()
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant required")
    bundle = Bundle(**payload)
    importer = FhirImporter(db)
    try:
        return importer.import_bundle(bundle, tenant_id=tenant_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/patient")
def import_patient(
    payload: dict[str, Any],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    _require_fhir()
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant required")
    patient = Patient(**payload)
    importer = FhirImporter(db)
    return importer.import_patient(patient, tenant_id=tenant_id, user_id=current_user.id)


@router.post("/from-ehr")
def import_from_ehr(
    body: EhrImportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    _require_fhir()
    if not settings.SMART_ENABLED and not body.client_id:
        raise HTTPException(status_code=400, detail="SMART on FHIR is disabled; provide client credentials")
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant required")

    client = SmartOnFhirClient(
        authorization_url=body.authorization_url,
        token_url=body.token_url,
        client_id=body.client_id,
        client_secret=body.client_secret,
        fhir_base_url=body.fhir_base_url,
    )
    try:
        patient_data = client.fetch_patient(body.ehr_patient_id)
        observations = client.fetch_observation(body.ehr_patient_id)
        encounters = client.fetch_encounter(body.ehr_patient_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"EHR fetch failed: {exc}") from exc

    importer = FhirImporter(db)
    patient = Patient(**patient_data)
    result = importer.import_patient(patient, tenant_id=tenant_id, user_id=current_user.id)
    pid = result["id"]

    from fhir.resources.bundle import Bundle as FhirBundle
    from fhir.resources.bundle import BundleEntry

    entries = [BundleEntry(resource=Patient(**patient_data))]
    for enc in encounters:
        from fhir.resources.encounter import Encounter

        entries.append(BundleEntry(resource=Encounter(**enc)))
    for obs in observations:
        from fhir.resources.observation import Observation

        entries.append(BundleEntry(resource=Observation(**obs)))
    bundle = FhirBundle(type="collection", entry=entries)
    bundle_result = importer.import_bundle(bundle, tenant_id=tenant_id, user_id=current_user.id)
    return {"patient": result, "bundle_import": bundle_result, "ehr_patient_id": body.ehr_patient_id, "local_patient_id": pid}
