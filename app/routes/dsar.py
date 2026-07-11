"""DSAR admin API — export and erasure for compliance."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.audit import log_audit
from app.services.audit_events import DSAR_ERASURE, DSAR_EXPORT
from app.services.dsar import build_patient_dsar_bundle, erase_patient_dsar, export_patient_dsar_json
from app.middleware.tenant import get_request_tenant_id
from app.services.access import effective_tenant_id

router = APIRouter(prefix="/admin/dsar", tags=["dsar"])


class DsarErasureResponse(BaseModel):
    detail: str
    patient_id: int


@router.get("/patients/{patient_id}/export")
def dsar_export_patient(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant required")
    try:
        payload = export_patient_dsar_json(db, patient_id, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=tenant_id,
        action=DSAR_EXPORT,
        resource_type="patient",
        resource_id=patient_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PlainTextResponse(payload, media_type="application/json")


@router.post("/patients/{patient_id}/erase", response_model=DsarErasureResponse)
def dsar_erase_patient(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant required")
    try:
        erase_patient_dsar(db, patient_id, tenant_id, actor=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=tenant_id,
        action=DSAR_ERASURE,
        resource_type="patient",
        resource_id=patient_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return DsarErasureResponse(detail="Patient data erased", patient_id=patient_id)
