"""Appointments calendar API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import Appointment, AppointmentHistory, AppointmentRecurring, AppointmentType, User
from app.services.access import WRITE_ROLES, effective_tenant_id, require_role
from app.services.appointment_service import AppointmentService
from app.services.audit import log_audit
from app.services.calendar_service import CalendarService
from app.utils.pagination import PaginationParams
from app.websocket.events import EVENT_APPOINTMENT_CREATED, EVENT_APPOINTMENT_UPDATED, publish_event

router = APIRouter(prefix="/appointments", tags=["appointments"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AppointmentTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    duration_minutes: int = Field(ge=5, le=480, default=30)
    color: str = Field(default="#3B82F6", max_length=16)
    is_active: bool = True


class AppointmentTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    color: str | None = Field(default=None, max_length=16)
    is_active: bool | None = None


class AppointmentTypeResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    duration_minutes: int
    color: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_type_id: int
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: int | None = None
    title: str | None = None
    description: str | None = None
    notes: str | None = None
    patient_document_id: int | None = None
    dicom_study_id: int | None = None
    prediction_id: int | None = None
    remind_before_minutes: int = Field(default=30, ge=0, le=1440)


class AppointmentUpdate(BaseModel):
    patient_id: int | None = None
    doctor_id: int | None = None
    appointment_type_id: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_minutes: int | None = None
    title: str | None = None
    description: str | None = None
    notes: str | None = None
    status: str | None = None
    patient_document_id: int | None = None
    dicom_study_id: int | None = None
    prediction_id: int | None = None
    remind_before_minutes: int | None = Field(default=None, ge=0, le=1440)


class AppointmentResponse(BaseModel):
    id: int
    tenant_id: int
    patient_id: int
    doctor_id: int
    created_by: int
    appointment_type_id: int
    status: str
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    title: str
    description: str | None
    notes: str | None
    patient_document_id: int | None
    dicom_study_id: int | None
    prediction_id: int | None
    remind_before_minutes: int
    reminder_sent: bool
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    patient_name: str | None = None
    doctor_name: str | None = None
    type_name: str | None = None
    type_color: str | None = None

    model_config = {"from_attributes": True}


class RecurringConfig(BaseModel):
    recurrence_type: str = Field(pattern="^(daily|weekly|monthly|custom)$")
    recurrence_interval: int = Field(default=1, ge=1)
    recurrence_days: list[int] | None = None
    recurrence_until: date | None = None
    recurrence_count: int | None = Field(default=None, ge=1)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CompleteRequest(BaseModel):
    notes: str = ""


class AppointmentListResponse(BaseModel):
    items: list[AppointmentResponse]
    total: int
    page: int
    page_size: int


class HistoryResponse(BaseModel):
    id: int
    appointment_id: int
    user_id: int
    previous_status: str
    new_status: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_enabled() -> None:
    if not settings.APPOINTMENTS_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Appointments disabled")


def _tenant_id(user: User, request: Request) -> int:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    if tid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant required")
    return tid


def _serialize(appt: Appointment) -> dict:
    data = AppointmentResponse.model_validate(appt).model_dump()
    if appt.patient:
        p = appt.patient
        data["patient_name"] = f"{p.last_name} {p.first_name}"
    if appt.doctor:
        data["doctor_name"] = appt.doctor.full_name
    if appt.appointment_type:
        data["type_name"] = appt.appointment_type.name
        data["type_color"] = appt.appointment_type.color
    return data


def _get_type_or_404(db: Session, type_id: int, tenant_id: int) -> AppointmentType:
    row = (
        db.query(AppointmentType)
        .filter(AppointmentType.id == type_id, AppointmentType.tenant_id == tenant_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment type not found")
    return row


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
@router.get("/types", response_model=list[AppointmentTypeResponse])
def list_appointment_types(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    svc = AppointmentService(db)
    svc.ensure_default_types(tenant_id)
    rows = (
        db.query(AppointmentType)
        .filter(AppointmentType.tenant_id == tenant_id, AppointmentType.is_active.is_(True))
        .order_by(AppointmentType.name)
        .all()
    )
    return rows


@router.post("/types", status_code=status.HTTP_201_CREATED, response_model=AppointmentTypeResponse)
def create_appointment_type(
    data: AppointmentTypeCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    existing = (
        db.query(AppointmentType)
        .filter(AppointmentType.tenant_id == tenant_id, AppointmentType.code == data.code)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Type code already exists")
    row = AppointmentType(tenant_id=tenant_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/types/{type_id}", response_model=AppointmentTypeResponse)
def update_appointment_type(
    type_id: int,
    data: AppointmentTypeUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    row = _get_type_or_404(db, type_id, tenant_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment_type(
    type_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    row = _get_type_or_404(db, type_id, tenant_id)
    row.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Export & schedule (before /{id})
# ---------------------------------------------------------------------------
@router.get("/export/ics")
def export_ics(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    date_from: date | None = None,
    date_to: date | None = None,
    doctor_id: int | None = None,
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    svc = AppointmentService(db)
    filters: dict = {}
    if date_from:
        filters["date_from"] = datetime.combine(date_from, datetime.min.time())
    if date_to:
        filters["date_to"] = datetime.combine(date_to, datetime.max.time())
    if doctor_id:
        filters["doctor_id"] = doctor_id
    appointments = svc.list_appointments(filters, tenant_id)
    ics = CalendarService().export_to_ics(appointments)
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="appointments.ics"'},
    )


@router.get("/export/google-calendar")
def google_calendar_link(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    appointment_id: int = Query(...),
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    appt = AppointmentService(db).get_appointment(appointment_id, tenant_id)
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return {"url": CalendarService().get_google_calendar_url(appt)}


@router.get("/doctors")
def list_assignable_doctors(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    doctors = AppointmentService(db).list_assignable_doctors(tenant_id)
    return [
        {"id": d.id, "full_name": d.full_name, "role": d.role, "email": d.email}
        for d in doctors
    ]


@router.get("/schedule/overview")
def schedule_overview(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    return AppointmentService(db).get_schedule_overview(start_date, end_date, tenant_id=tenant_id)


@router.get("/schedule/available-slots")
def available_slots(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    doctor_id: int = Query(...),
    date: date = Query(...),
    duration: int | None = Query(default=None, ge=5, le=480),
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    slots = AppointmentService(db).get_available_slots(
        doctor_id, date, duration, tenant_id=tenant_id
    )
    return {"doctor_id": doctor_id, "date": date.isoformat(), "slots": slots}


@router.get("/schedule/doctor/{doctor_id}")
def doctor_schedule(
    doctor_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    schedule = AppointmentService(db).get_doctor_schedule(
        doctor_id, start_date, end_date, tenant_id=tenant_id
    )
    schedule["appointments"] = [_serialize(a) for a in schedule["appointments"]]
    return schedule


@router.get("/history/{appointment_id}", response_model=list[HistoryResponse])
def appointment_history(
    appointment_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    appt = AppointmentService(db).get_appointment(appointment_id, tenant_id)
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return (
        db.query(AppointmentHistory)
        .filter(AppointmentHistory.appointment_id == appointment_id)
        .order_by(AppointmentHistory.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Recurring
# ---------------------------------------------------------------------------
@router.put("/recurring/{recurring_id}")
def update_recurring_rule(
    recurring_id: int,
    data: RecurringConfig,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    row = (
        db.query(AppointmentRecurring)
        .filter(AppointmentRecurring.id == recurring_id, AppointmentRecurring.tenant_id == tenant_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring rule not found")
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "is_active": row.is_active}


@router.delete("/recurring/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_recurring(
    recurring_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    row = (
        db.query(AppointmentRecurring)
        .filter(AppointmentRecurring.id == recurring_id, AppointmentRecurring.tenant_id == tenant_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring rule not found")
    row.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED, response_model=AppointmentResponse)
def create_appointment(
    data: AppointmentCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    svc = AppointmentService(db)
    appt = svc.create_appointment(data.model_dump(), tenant_id=tenant_id, created_by=current_user.id)
    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=tenant_id,
        action="appointment.create",
        resource_type="appointment",
        resource_id=appt.id,
        ip_address=request.client.host if request.client else None,
    )
    publish_event(
        EVENT_APPOINTMENT_CREATED,
        {"appointment_id": appt.id, "title": appt.title, "start_time": appt.start_time.isoformat()},
        user_id=appt.doctor_id,
        tenant_id=tenant_id,
    )
    appt = svc.get_appointment(appt.id, tenant_id)
    return _serialize(appt)


@router.get("", response_model=AppointmentListResponse)
def list_appointments(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    doctor_id: int | None = None,
    patient_id: int | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    appointment_type_id: int | None = None,
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    filters: dict = {}
    if doctor_id:
        filters["doctor_id"] = doctor_id
    if patient_id:
        filters["patient_id"] = patient_id
    if status:
        filters["status"] = status
    if date_from:
        filters["date_from"] = datetime.combine(date_from, datetime.min.time())
    if date_to:
        filters["date_to"] = datetime.combine(date_to, datetime.max.time())
    if appointment_type_id:
        filters["appointment_type_id"] = appointment_type_id

    query = (
        db.query(Appointment)
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor),
            joinedload(Appointment.appointment_type),
        )
        .filter(Appointment.tenant_id == tenant_id)
    )
    if filters.get("doctor_id"):
        query = query.filter(Appointment.doctor_id == filters["doctor_id"])
    if filters.get("patient_id"):
        query = query.filter(Appointment.patient_id == filters["patient_id"])
    if filters.get("status"):
        query = query.filter(Appointment.status == filters["status"])
    if filters.get("date_from"):
        query = query.filter(Appointment.start_time >= filters["date_from"])
    if filters.get("date_to"):
        query = query.filter(Appointment.start_time <= filters["date_to"])
    if filters.get("appointment_type_id"):
        query = query.filter(Appointment.appointment_type_id == filters["appointment_type_id"])

    query = query.order_by(Appointment.start_time.asc())
    pagination = PaginationParams(page=page, limit=limit)
    total = query.count()
    offset = (pagination.page - 1) * pagination.limit
    rows = query.offset(offset).limit(pagination.limit).all()
    return AppointmentListResponse(
        items=[_serialize(a) for a in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.limit,
    )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    appt = AppointmentService(db).get_appointment(appointment_id, tenant_id)
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return _serialize(appt)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(
    appointment_id: int,
    data: AppointmentUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    appt = AppointmentService(db).update_appointment(
        appointment_id, data.model_dump(exclude_unset=True), tenant_id=tenant_id, user_id=current_user.id
    )
    publish_event(
        EVENT_APPOINTMENT_UPDATED,
        {"appointment_id": appt.id, "status": appt.status},
        user_id=appt.doctor_id,
        tenant_id=tenant_id,
    )
    appt = AppointmentService(db).get_appointment(appt.id, tenant_id)
    return _serialize(appt)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(
    appointment_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    AppointmentService(db).cancel_appointment(
        appointment_id, "deleted", current_user.id, tenant_id=tenant_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    appointment_id: int,
    data: CancelRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    appt = AppointmentService(db).cancel_appointment(
        appointment_id, data.reason, current_user.id, tenant_id=tenant_id
    )
    appt = AppointmentService(db).get_appointment(appt.id, tenant_id)
    return _serialize(appt)


@router.post("/{appointment_id}/confirm", response_model=AppointmentResponse)
def confirm_appointment(
    appointment_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    tenant_id = _tenant_id(current_user, request)
    appt = AppointmentService(db).confirm_appointment(
        appointment_id, current_user.id, tenant_id=tenant_id
    )
    appt = AppointmentService(db).get_appointment(appt.id, tenant_id)
    return _serialize(appt)


@router.post("/{appointment_id}/complete", response_model=AppointmentResponse)
def complete_appointment(
    appointment_id: int,
    data: CompleteRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    appt = AppointmentService(db).complete_appointment(
        appointment_id, data.notes, tenant_id=tenant_id, user_id=current_user.id
    )
    appt = AppointmentService(db).get_appointment(appt.id, tenant_id)
    return _serialize(appt)


@router.post("/{appointment_id}/recurring")
def create_recurring(
    appointment_id: int,
    data: RecurringConfig,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    _require_enabled()
    require_role(current_user, *WRITE_ROLES)
    tenant_id = _tenant_id(current_user, request)
    created = AppointmentService(db).create_recurring_appointments(
        appointment_id, data.model_dump(), tenant_id=tenant_id
    )
    return {"created": len(created), "appointment_ids": [a.id for a in created]}
