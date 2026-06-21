from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import get_current_user
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import Department, Document, Patient, User
from app.services.access import (
    anonymize_patient,
    can_create_patient,
    can_delete_patient,
    can_modify_patient,
    can_view_patient,
    effective_tenant_id,
    patients_query,
)
from app.services.list_queries import PATIENT_SEARCH_FIELDS, PATIENT_SORT, patients_scope
from app.utils.pagination import PaginationParams, paginate

router = APIRouter(prefix="/patients", tags=["patients"])


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date
    gender: str = Field(pattern="^(M|F|O)$")
    phone: str = Field(min_length=1, max_length=50)
    email: EmailStr | None = None
    department_id: int
    attending_doctor_id: int | None = None


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date | None = None
    gender: str | None = Field(default=None, pattern="^(M|F|O)$")
    phone: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = None
    department_id: int | None = None
    attending_doctor_id: int | None = None


class PatientResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    department_id: int | None = None
    attending_doctor_id: int | None = None
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

    # Department is mandatory and must belong to the patient's tenant.
    dept = db.query(Department).filter(Department.id == data.department_id).first()
    if not dept or dept.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department for tenant")

    # Department-scoped roles may only create patients within their own department.
    if current_user.role in ("doctor", "head_of_department") and not getattr(
        current_user, "can_see_all_patients", False
    ):
        if current_user.department_id is not None and current_user.department_id != data.department_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create patients outside your department",
            )

    attending_doctor_id = data.attending_doctor_id
    if attending_doctor_id is None and current_user.role in ("doctor", "head_of_department"):
        attending_doctor_id = current_user.id

    payload = data.model_dump(exclude={"attending_doctor_id"})
    patient = Patient(
        tenant_id=tenant_id,
        user_id=current_user.id,
        attending_doctor_id=attending_doctor_id,
        **payload,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    if settings.TELEGRAM_BOT_ENABLED:
        try:
            from app.bot.services.notification_service import get_notification_service

            name = f"{patient.last_name} {patient.first_name}".strip()
            get_notification_service().send_patient_created_sync(
                user_id=current_user.id,
                patient_name=name,
                patient_id=patient.id,
            )
        except Exception:  # noqa: BLE001 — notifications must not fail the request
            pass

    return _serialize_patient(patient, current_user)


@router.get("")
def list_patients(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    page_size: int | None = Query(None, ge=1, le=100, description="Алиас limit (совместимость)"),
    search: str | None = Query(None),
    department_id: int | None = Query(None),
    attending_doctor_id: int | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    query = patients_scope(db, current_user, tid)
    params = PaginationParams(
        page=page,
        limit=page_size or limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={"department_id": department_id, "attending_doctor_id": attending_doctor_id},
    )
    result = paginate(
        query,
        params,
        model=Patient,
        search_fields=PATIENT_SEARCH_FIELDS,
        allowed_sort=PATIENT_SORT,
        serializer=lambda p: _serialize_patient(p, current_user),
    )
    # Back-compat alias for older clients that read page_size.
    result["page_size"] = result["limit"]
    return result


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
