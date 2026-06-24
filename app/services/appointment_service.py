"""Business logic for patient appointments."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import (
    Appointment,
    AppointmentHistory,
    AppointmentRecurring,
    AppointmentType,
    Patient,
    User,
)
from app.services.recurring_service import RecurringService
from app.services.reminder_service import ReminderService

APPOINTMENT_STATUSES = frozenset(
    {"scheduled", "confirmed", "in_progress", "completed", "cancelled", "no_show"}
)
ACTIVE_SLOT_STATUSES = frozenset({"scheduled", "confirmed", "in_progress"})

DEFAULT_TYPES = [
    {"name": "Первичный приём", "code": "primary", "duration_minutes": 60, "color": "#3B82F6"},
    {"name": "Повторный приём", "code": "follow_up", "duration_minutes": 30, "color": "#10B981"},
    {"name": "Консультация", "code": "consultation", "duration_minutes": 45, "color": "#8B5CF6"},
    {"name": "Процедура", "code": "procedure", "duration_minutes": 90, "color": "#F59E0B"},
]


class AppointmentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._recurring = RecurringService()
        self._reminders = ReminderService(db)

    def ensure_default_types(self, tenant_id: int) -> None:
        existing = (
            self.db.query(AppointmentType)
            .filter(AppointmentType.tenant_id == tenant_id)
            .count()
        )
        if existing:
            return
        for row in DEFAULT_TYPES:
            self.db.add(AppointmentType(tenant_id=tenant_id, **row))
        self.db.commit()

    def _validate_booking_window(self, start_time: datetime) -> None:
        now = datetime.utcnow()
        min_start = now + timedelta(hours=settings.APPOINTMENTS_MIN_BOOKING_HOURS)
        max_start = now + timedelta(days=settings.APPOINTMENTS_MAX_BOOKING_DAYS)
        if start_time < min_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Приём должен быть не ранее чем через {settings.APPOINTMENTS_MIN_BOOKING_HOURS} ч.",
            )
        if start_time > max_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Приём не может быть позже чем через {settings.APPOINTMENTS_MAX_BOOKING_DAYS} дн.",
            )

    def _has_conflict(
        self,
        doctor_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_id: int | None = None,
    ) -> bool:
        query = self.db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.status.in_(ACTIVE_SLOT_STATUSES),
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
        )
        if exclude_id:
            query = query.filter(Appointment.id != exclude_id)
        return query.first() is not None

    def _record_history(
        self,
        appointment: Appointment,
        user_id: int,
        previous_status: str,
        new_status: str,
        notes: str | None = None,
    ) -> None:
        self.db.add(
            AppointmentHistory(
                appointment_id=appointment.id,
                user_id=user_id,
                previous_status=previous_status,
                new_status=new_status,
                notes=notes,
            )
        )

    def _build_title(self, patient: Patient, appt_type: AppointmentType) -> str:
        name = f"{patient.last_name} {patient.first_name}"
        if patient.middle_name:
            name += f" {patient.middle_name}"
        return f"{name}, {appt_type.name}"

    def create_appointment(self, data: dict, *, tenant_id: int, created_by: int) -> Appointment:
        if not settings.APPOINTMENTS_ENABLED:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Appointments disabled")

        self.ensure_default_types(tenant_id)
        patient = self.db.query(Patient).filter(Patient.id == data["patient_id"], Patient.tenant_id == tenant_id).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        doctor = self.db.query(User).filter(User.id == data["doctor_id"], User.tenant_id == tenant_id).first()
        if not doctor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

        appt_type = (
            self.db.query(AppointmentType)
            .filter(
                AppointmentType.id == data["appointment_type_id"],
                AppointmentType.tenant_id == tenant_id,
                AppointmentType.is_active.is_(True),
            )
            .first()
        )
        if not appt_type:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment type not found")

        start_time = data["start_time"]
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace("Z", ""))
        duration = int(data.get("duration_minutes") or appt_type.duration_minutes)
        end_time = data.get("end_time")
        if end_time is None:
            end_time = start_time + timedelta(minutes=duration)
        elif isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace("Z", ""))

        self._validate_booking_window(start_time)
        if self._has_conflict(data["doctor_id"], start_time, end_time):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Doctor schedule conflict")

        remind = int(data.get("remind_before_minutes") or 30)
        appointment = Appointment(
            tenant_id=tenant_id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            created_by=created_by,
            appointment_type_id=appt_type.id,
            status=data.get("status") or "scheduled",
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            title=data.get("title") or self._build_title(patient, appt_type),
            description=data.get("description"),
            notes=data.get("notes"),
            patient_document_id=data.get("patient_document_id"),
            dicom_study_id=data.get("dicom_study_id"),
            prediction_id=data.get("prediction_id"),
            remind_before_minutes=remind,
        )
        self.db.add(appointment)
        self.db.flush()
        self._record_history(appointment, created_by, "", appointment.status, notes="created")
        self.db.commit()
        self.db.refresh(appointment)
        self._reminders.schedule_reminder(appointment.id)
        return appointment

    def get_appointment(self, appointment_id: int, tenant_id: int) -> Appointment | None:
        return (
            self.db.query(Appointment)
            .options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor),
                joinedload(Appointment.appointment_type),
            )
            .filter(Appointment.id == appointment_id, Appointment.tenant_id == tenant_id)
            .first()
        )

    def list_appointments(self, filters: dict, tenant_id: int) -> list[Appointment]:
        query = (
            self.db.query(Appointment)
            .options(joinedload(Appointment.patient), joinedload(Appointment.appointment_type))
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
        return query.order_by(Appointment.start_time.asc()).all()

    def get_appointments_for_doctor(self, doctor_id: int, day: date, tenant_id: int) -> list[Appointment]:
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        return (
            self.db.query(Appointment)
            .options(joinedload(Appointment.patient), joinedload(Appointment.appointment_type))
            .filter(
                Appointment.tenant_id == tenant_id,
                Appointment.doctor_id == doctor_id,
                Appointment.start_time >= start,
                Appointment.start_time <= end,
            )
            .order_by(Appointment.start_time)
            .all()
        )

    def get_appointments_for_patient(self, patient_id: int, tenant_id: int) -> list[Appointment]:
        return (
            self.db.query(Appointment)
            .options(joinedload(Appointment.doctor), joinedload(Appointment.appointment_type))
            .filter(Appointment.tenant_id == tenant_id, Appointment.patient_id == patient_id)
            .order_by(Appointment.start_time.desc())
            .all()
        )

    def update_appointment(self, appointment_id: int, data: dict, *, tenant_id: int, user_id: int) -> Appointment:
        appointment = self.get_appointment(appointment_id, tenant_id)
        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        if appointment.status in ("cancelled", "completed"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot update finished appointment")

        previous_status = appointment.status
        if "start_time" in data and data["start_time"]:
            start = data["start_time"]
            if isinstance(start, str):
                start = datetime.fromisoformat(start.replace("Z", ""))
            appointment.start_time = start
            self._validate_booking_window(start)
        if "duration_minutes" in data and data["duration_minutes"]:
            appointment.duration_minutes = int(data["duration_minutes"])
        if "end_time" in data and data["end_time"]:
            end = data["end_time"]
            if isinstance(end, str):
                end = datetime.fromisoformat(end.replace("Z", ""))
            appointment.end_time = end
        elif "start_time" in data or "duration_minutes" in data:
            appointment.end_time = appointment.start_time + timedelta(minutes=appointment.duration_minutes)

        if self._has_conflict(
            appointment.doctor_id, appointment.start_time, appointment.end_time, exclude_id=appointment.id
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Doctor schedule conflict")

        for field in (
            "title", "description", "notes", "doctor_id", "patient_id",
            "appointment_type_id", "patient_document_id", "dicom_study_id",
            "prediction_id", "remind_before_minutes",
        ):
            if field in data and data[field] is not None:
                setattr(appointment, field, data[field])
        if "status" in data and data["status"] in APPOINTMENT_STATUSES:
            appointment.status = data["status"]

        appointment.updated_at = datetime.utcnow()
        if appointment.status != previous_status:
            self._record_history(appointment, user_id, previous_status, appointment.status)
        self.db.commit()
        self.db.refresh(appointment)
        if "start_time" in data or "remind_before_minutes" in data:
            self._reminders.schedule_reminder(appointment.id)
        return appointment

    def cancel_appointment(
        self, appointment_id: int, reason: str, user_id: int, *, tenant_id: int
    ) -> Appointment:
        appointment = self.get_appointment(appointment_id, tenant_id)
        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        previous = appointment.status
        appointment.status = "cancelled"
        appointment.cancelled_at = datetime.utcnow()
        appointment.cancelled_by = user_id
        appointment.cancellation_reason = reason
        self._record_history(appointment, user_id, previous, "cancelled", notes=reason)
        self.db.commit()
        self.db.refresh(appointment)
        return appointment

    def confirm_appointment(self, appointment_id: int, user_id: int, *, tenant_id: int) -> Appointment:
        appointment = self.get_appointment(appointment_id, tenant_id)
        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        previous = appointment.status
        appointment.status = "confirmed"
        self._record_history(appointment, user_id, previous, "confirmed")
        self.db.commit()
        self.db.refresh(appointment)
        return appointment

    def complete_appointment(
        self, appointment_id: int, notes: str, *, tenant_id: int, user_id: int
    ) -> Appointment:
        appointment = self.get_appointment(appointment_id, tenant_id)
        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        previous = appointment.status
        appointment.status = "completed"
        if notes:
            appointment.notes = (appointment.notes or "") + ("\n" if appointment.notes else "") + notes
        self._record_history(appointment, user_id, previous, "completed", notes=notes)
        self.db.commit()
        self.db.refresh(appointment)
        return appointment

    def get_doctor_schedule(
        self, doctor_id: int, start_date: date, end_date: date, *, tenant_id: int
    ) -> dict:
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)
        appointments = (
            self.db.query(Appointment)
            .options(joinedload(Appointment.patient), joinedload(Appointment.appointment_type))
            .filter(
                Appointment.tenant_id == tenant_id,
                Appointment.doctor_id == doctor_id,
                Appointment.start_time >= start_dt,
                Appointment.start_time <= end_dt,
            )
            .order_by(Appointment.start_time)
            .all()
        )
        doctor = self.db.query(User).filter(User.id == doctor_id).first()
        return {
            "doctor_id": doctor_id,
            "doctor_name": doctor.full_name if doctor else None,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "appointments": appointments,
            "total": len(appointments),
        }

    def get_available_slots(
        self, doctor_id: int, day: date, duration: int | None = None, *, tenant_id: int
    ) -> list[dict]:
        slot_minutes = duration or settings.APPOINTMENTS_SLOT_DURATION_MINUTES
        work_start = time(settings.APPOINTMENTS_WORK_START_HOUR, 0)
        work_end = time(settings.APPOINTMENTS_WORK_END_HOUR, 0)
        day_start = datetime.combine(day, work_start)
        day_end = datetime.combine(day, work_end)

        busy = self.get_appointments_for_doctor(doctor_id, day, tenant_id)
        busy_intervals = [
            (a.start_time, a.end_time)
            for a in busy
            if a.status in ACTIVE_SLOT_STATUSES
        ]

        slots: list[dict] = []
        cursor = day_start
        delta = timedelta(minutes=slot_minutes)
        while cursor + delta <= day_end:
            slot_end = cursor + delta
            conflict = any(start < slot_end and end > cursor for start, end in busy_intervals)
            if not conflict:
                try:
                    self._validate_booking_window(cursor)
                    slots.append(
                        {
                            "start_time": cursor.isoformat(),
                            "end_time": slot_end.isoformat(),
                            "duration_minutes": slot_minutes,
                        }
                    )
                except HTTPException:
                    pass
            cursor += delta
        return slots

    def create_recurring_appointments(
        self, appointment_id: int, config: dict, *, tenant_id: int
    ) -> list[Appointment]:
        source = self.get_appointment(appointment_id, tenant_id)
        if not source:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        existing = (
            self.db.query(AppointmentRecurring)
            .filter(AppointmentRecurring.appointment_id == appointment_id)
            .first()
        )
        if existing:
            for key in (
                "recurrence_type", "recurrence_interval", "recurrence_days",
                "recurrence_until", "recurrence_count", "is_active",
            ):
                if key in config:
                    setattr(existing, key, config[key])
            existing.is_active = config.get("is_active", True)
            rule_row = existing
        else:
            rule_row = AppointmentRecurring(
                tenant_id=tenant_id,
                appointment_id=appointment_id,
                recurrence_type=config.get("recurrence_type", "weekly"),
                recurrence_interval=int(config.get("recurrence_interval", 1)),
                recurrence_days=config.get("recurrence_days"),
                recurrence_until=config.get("recurrence_until"),
                recurrence_count=config.get("recurrence_count"),
                is_active=True,
            )
            self.db.add(rule_row)
            self.db.commit()
            self.db.refresh(rule_row)

        return self._recurring.create_appointments_from_rule(self.db, source, rule_row)

    def mark_no_shows(self) -> int:
        """Mark past scheduled/confirmed appointments as no_show."""
        now = datetime.utcnow()
        grace = timedelta(minutes=30)
        rows = (
            self.db.query(Appointment)
            .filter(
                Appointment.status.in_(("scheduled", "confirmed")),
                Appointment.end_time < now - grace,
            )
            .all()
        )
        count = 0
        for appt in rows:
            previous = appt.status
            appt.status = "no_show"
            self._record_history(appt, appt.doctor_id, previous, "no_show", notes="auto")
            count += 1
        if count:
            self.db.commit()
        return count

    def get_schedule_overview(self, start_date: date, end_date: date, *, tenant_id: int) -> dict:
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)
        doctors = self.db.query(User).filter(User.tenant_id == tenant_id, User.role.in_(("doctor", "head_of_department"))).all()
        overview = []
        for doc in doctors:
            appts = (
                self.db.query(Appointment)
                .filter(
                    Appointment.tenant_id == tenant_id,
                    Appointment.doctor_id == doc.id,
                    Appointment.start_time >= start_dt,
                    Appointment.start_time <= end_dt,
                    Appointment.status != "cancelled",
                )
                .count()
            )
            overview.append({"doctor_id": doc.id, "doctor_name": doc.full_name, "appointment_count": appts})
        return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "doctors": overview}
