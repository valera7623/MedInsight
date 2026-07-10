"""ORM models — patient."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.db.types import PortableJSON, PortableTSVector, PortableUUID, uuid_default
from app.models._time import utc_now


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        Index("ix_patients_tenant_last_name", "tenant_id", "last_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(PortableUUID, default=uuid_default, unique=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    department_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    attending_doctor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(1), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(PortableTSVector, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="patients")
    owner: Mapped["User"] = relationship("User", back_populates="patients", foreign_keys="Patient.user_id")
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="patient", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        "Prediction", back_populates="patient", cascade="all, delete-orphan"
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob", back_populates="patient", cascade="all, delete-orphan"
    )

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_patient_status", "patient_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(PortableUUID, default=uuid_default, unique=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="discharge")
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parsed_data: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(PortableTSVector, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parsed_by_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parse_confidence: Mapped[float | None] = mapped_column(nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="documents")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="documents")
    owner: Mapped["User"] = relationship("User", back_populates="documents")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship("AnalysisJob", back_populates="document")

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("documents.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="analysis_jobs")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="analysis_jobs")
    owner: Mapped["User"] = relationship("User", back_populates="analysis_jobs")
    document: Mapped["Document | None"] = relationship("Document", back_populates="analysis_jobs")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="analysis_job")

class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    analysis_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("analysis_jobs.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="readmission")
    features: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    prediction: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    probabilities: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="predictions")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="predictions")
    owner: Mapped["User"] = relationship("User", back_populates="predictions")
    analysis_job: Mapped["AnalysisJob | None"] = relationship("AnalysisJob", back_populates="predictions")

class AppointmentType(Base):
    """Тип приёма (первичный, повторный, консультация, процедура и т.д.)."""

    __tablename__ = "appointment_types"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_appointment_type_tenant_code"),
        Index("ix_appointment_types_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#3B82F6")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", foreign_keys=[tenant_id])
    appointments: Mapped[list["Appointment"]] = relationship("Appointment", back_populates="appointment_type")

class Appointment(Base):
    """Основная запись о приёме."""

    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_doctor_start", "doctor_id", "start_time"),
        Index("ix_appointments_patient_start", "patient_id", "start_time"),
        Index("ix_appointments_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    appointment_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("appointment_types.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id"), nullable=True, index=True
    )
    dicom_study_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dicom_studies.id"), nullable=True, index=True
    )
    prediction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("predictions.id"), nullable=True, index=True
    )
    remind_before_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", foreign_keys=[patient_id])
    doctor: Mapped["User"] = relationship("User", foreign_keys=[doctor_id])
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    appointment_type: Mapped["AppointmentType"] = relationship("AppointmentType", back_populates="appointments")
    history: Mapped[list["AppointmentHistory"]] = relationship(
        "AppointmentHistory", back_populates="appointment", cascade="all, delete-orphan"
    )
    recurring: Mapped["AppointmentRecurring | None"] = relationship(
        "AppointmentRecurring", back_populates="appointment", uselist=False, cascade="all, delete-orphan"
    )

class AppointmentRecurring(Base):
    """Настройка повторяющихся приёмов."""

    __tablename__ = "appointment_recurring"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    appointment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("appointments.id"), nullable=False, unique=True, index=True
    )
    recurrence_type: Mapped[str] = mapped_column(String(32), nullable=False, default="weekly")
    recurrence_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recurrence_days: Mapped[list | None] = mapped_column(PortableJSON, nullable=True)
    recurrence_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    recurrence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="recurring")

class AppointmentHistory(Base):
    """История изменений статуса приёма."""

    __tablename__ = "appointment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    appointment_id: Mapped[int] = mapped_column(Integer, ForeignKey("appointments.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    previous_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="history")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
