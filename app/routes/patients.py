from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import Document, Patient, User
from app.services.access import (
    anonymize_patient,
    can_create_patient,
    can_delete_patient,
    can_modify_patient,
    can_view_patient,
    effective_tenant_id,
    patients_query,
)

router = APIRouter(prefix="/patients", tags=["patients"])


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date
    gender: str = Field(pattern="^(M|F|O)$")
    phone: str = Field(min_length=1, max_length=50)
    email: EmailStr | None = None


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date | None = None
    gender: str | None = Field(default=None, pattern="^(M|F|O)$")
    phone: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = None


class PatientResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    first_name: str
    last_name: str
    middle_name: str | None
    birth_date: date
    gender: str
    phone: str
    email: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientListResponse(BaseModel):
    items: list[PatientResponse]
    total: int
    page: int
    page_size: int


def _serialize_patient(patient: Patient, user: User) -> dict:
    if user.role == "researcher":
        return anonymize_patient(patient)
    return PatientResponse.model_validate(patient).model_dump()


def _get_patient_or_404(
    db: Session, patient_id: int, user: User, request: Request | None = None
) -> Patient:
    tid = effective_tenant_id(user, get_request_tenant_id(request) if request else None)
    query = db.query(Patient).filter(Patient.id == patient_id)
    if tid is not None:
        query = query.filter(Patient.tenant_id == tid)
    patient = query.first()
    if not patient or not can_view_patient(user, patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@router.post("", status_code=status.HTTP_201_CREATED)
def create_patient(
    data: PatientCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_create_patient(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create patients")

    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant required")

    patient = Patient(tenant_id=tenant_id, user_id=current_user.id, **data.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return _serialize_patient(patient, current_user)


@router.get("", response_model=PatientListResponse)
def list_patients(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    query = patients_query(db, current_user, tid)
    total = query.count()
    items = (
        query.order_by(Patient.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PatientListResponse(
        items=[_serialize_patient(p, current_user) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{patient_id}")
def get_patient(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = _get_patient_or_404(db, patient_id, current_user, request)
    return _serialize_patient(patient, current_user)


@router.put("/{patient_id}")
def update_patient(
    patient_id: int,
    data: PatientUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = _get_patient_or_404(db, patient_id, current_user, request)
    if not can_modify_patient(current_user, patient):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this patient")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    patient.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(patient)

    try:
        from app.tasks.webhook_task import fire_event

        fire_event("patient.updated", patient.tenant_id, patient_id=patient.id)
    except Exception:
        pass

    return _serialize_patient(patient, current_user)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_delete_patient(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete patients")

    patient = _get_patient_or_404(db, patient_id, current_user, request)

    documents = db.query(Document).filter(Document.patient_id == patient_id).all()
    for doc in documents:
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(doc)

    db.delete(patient)
    db.commit()
