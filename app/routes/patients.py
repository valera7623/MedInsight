from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Document, Patient, User

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


def _get_patient_or_404(db: Session, patient_id: int, user_id: int) -> Patient:
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id, Patient.user_id == user_id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    data: PatientCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = Patient(user_id=current_user.id, **data.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=PatientListResponse)
def list_patients(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Patient).filter(Patient.user_id == current_user.id)
    total = query.count()
    items = (
        query.order_by(Patient.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PatientListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return _get_patient_or_404(db, patient_id, current_user.id)


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: int,
    data: PatientUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = _get_patient_or_404(db, patient_id, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    patient.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(
    patient_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    documents = db.query(Document).filter(Document.patient_id == patient_id).all()
    for doc in documents:
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(doc)

    db.delete(patient)
    db.commit()
