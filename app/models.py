"""SQLAlchemy ORM models — JSONB/UUID on PostgreSQL, JSON on SQLite."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.db.types import PortableJSON, PortableTSVector, PortableUUID, uuid_default


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(PortableUUID, default=uuid_default, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    settings: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")
    patients: Mapped[list["Patient"]] = relationship("Patient", back_populates="tenant")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="tenant")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="tenant")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship("AnalysisJob", back_populates="tenant")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="tenant")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    head_doctor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(PortableUUID, default=uuid_default, unique=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    department_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="doctor")
    can_see_all_patients: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="users")
    patients: Mapped[list["Patient"]] = relationship(
        "Patient", back_populates="owner", foreign_keys="Patient.user_id"
    )
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="owner")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="owner")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship("AnalysisJob", back_populates="owner")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")
    preferences: Mapped["UserPreference | None"] = relationship(
        "UserPreference", back_populates="user", uselist=False
    )


class UserPreference(Base):
    """Per-user UI preferences (Phase 11: Dark Mode)."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="light")
    system_theme: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="preferences")


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="predictions")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="predictions")
    owner: Mapped["User"] = relationship("User", back_populates="predictions")
    analysis_job: Mapped["AnalysisJob | None"] = relationship("AnalysisJob", back_populates="predictions")


class AuditLog(Base):
    """Append-only audit event log (SIEM export + cryptographic signing)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_export_status", "export_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    details: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    # SIEM export & signing (Phase 13)
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    export_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    export_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_export_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    export_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")
    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="audit_logs")
    export_logs: Mapped[list["AuditExportLog"]] = relationship(
        "AuditExportLog", back_populates="event", cascade="all, delete-orphan"
    )


# Alias for SIEM / security documentation
AuditEvent = AuditLog


class AuditExportLog(Base):
    """Record of each SIEM export attempt for an audit event."""

    __tablename__ = "audit_export_logs"
    __table_args__ = (
        Index("ix_audit_export_logs_event_created", "event_id", "created_at"),
        Index("ix_audit_export_logs_target_status", "target", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("audit_logs.id"), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False)  # syslog | cef | splunk_hec | jsonl
    target: Mapped[str] = mapped_column(String(50), nullable=False)  # splunk | sentinel | log360 | securonix
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failed
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    event: Mapped["AuditLog"] = relationship("AuditLog", back_populates="export_logs")


class AuditKey(Base):
    """Encrypted signing key for audit event integrity."""

    __tablename__ = "audit_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Phase 14: HL7 FHIR interoperability
# ---------------------------------------------------------------------------


class FhirMapping(Base):
    """Maps MedInsight internal IDs to FHIR resource identifiers."""

    __tablename__ = "fhir_mapping"
    __table_args__ = (
        Index("ix_fhir_mapping_resource_medinsight", "resource_type", "medinsight_id"),
        UniqueConstraint("resource_type", "medinsight_id", name="uq_fhir_mapping_resource_medinsight"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    medinsight_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    fhir_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    fhir_version: Mapped[str] = mapped_column(String(10), nullable=False, default="R4")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Phase 15: PDF report templates
# ---------------------------------------------------------------------------


class ReportTemplate(Base):
    """Jinja2 HTML template for PDF clinical reports."""

    __tablename__ = "report_templates"
    __table_args__ = (Index("ix_report_templates_tenant_type", "tenant_id", "template_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    template_html: Mapped[str] = mapped_column(Text, nullable=False)
    template_css: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    variables: Mapped[list["ReportTemplateVariable"]] = relationship(
        "ReportTemplateVariable", back_populates="template", cascade="all, delete-orphan"
    )
    reports: Mapped[list["GeneratedReport"]] = relationship("GeneratedReport", back_populates="template")


class ReportTemplateVariable(Base):
    """Declared variable for a report template."""

    __tablename__ = "report_template_variables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("report_templates.id"), nullable=False, index=True
    )
    variable_name: Mapped[str] = mapped_column(String(100), nullable=False)
    variable_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    variable_description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped["ReportTemplate"] = relationship("ReportTemplate", back_populates="variables")


class GeneratedReport(Base):
    """Generated PDF report instance."""

    __tablename__ = "generated_reports"
    __table_args__ = (Index("ix_generated_reports_patient_created", "patient_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_templates.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    report_data: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped["ReportTemplate"] = relationship("ReportTemplate", back_populates="reports")


# ---------------------------------------------------------------------------
# Phase 4: Self-healing RAG, Webhooks, Payments
# ---------------------------------------------------------------------------


class ErrorFix(Base):
    """Self-healing knowledge base record (also indexed in ChromaDB)."""

    __tablename__ = "error_fixes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    error_text: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown", index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown", index=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution_code: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    was_successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    events: Mapped[list | None] = mapped_column(PortableJSON, nullable=True, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yookassa_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_type: Mapped[str] = mapped_column(String(50), nullable=False, default="freemium")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    reports_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    reports_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_period_start: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="RUB")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TelegramUser(Base):
    """Linked Telegram account for MedInsight user notifications (Phase 10)."""

    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subscription_events: Mapped[list] = mapped_column(
        PortableJSON,
        nullable=False,
        default=lambda: ["prediction.ready", "analysis.completed"],
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class DicomStudy(Base):
    """DICOM study metadata (Phase 12)."""

    __tablename__ = "dicom_studies"
    __table_args__ = (
        Index("ix_dicom_studies_patient_modality", "patient_id", "modality"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    study_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    study_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    study_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    body_part: Mapped[str | None] = mapped_column(String(128), nullable=True)
    patient_name_dicom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    patient_id_dicom: Mapped[str | None] = mapped_column(String(128), nullable=True)
    num_series: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_path_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(PortableTSVector, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zip_original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip_size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    radiology_findings: Mapped[list | None] = mapped_column(PortableJSON, nullable=True)
    radiology_impression: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_measurements: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    clinical_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinical_context_processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", foreign_keys=[patient_id])
    series: Mapped[list["DicomSeries"]] = relationship(
        "DicomSeries", back_populates="study", cascade="all, delete-orphan"
    )


class DicomSeries(Base):
    __tablename__ = "dicom_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    study_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_studies.id"), nullable=False, index=True)
    series_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    series_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    num_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    study: Mapped["DicomStudy"] = relationship("DicomStudy", back_populates="series")
    frames: Mapped[list["DicomFrame"]] = relationship(
        "DicomFrame", back_populates="series", cascade="all, delete-orphan"
    )


class DicomFrame(Base):
    __tablename__ = "dicom_frames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_series.id"), nullable=False, index=True)
    instance_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pixel_spacing: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    series: Mapped["DicomSeries"] = relationship("DicomSeries", back_populates="frames")
    annotations: Mapped[list["DicomAnnotation"]] = relationship(
        "DicomAnnotation", back_populates="frame", cascade="all, delete-orphan"
    )


class DicomAnnotation(Base):
    """User-drawn markup on a DICOM frame (Phase 12c)."""

    __tablename__ = "dicom_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    frame_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_frames.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    coordinates: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#FF0000")
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    measurement_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    frame: Mapped["DicomFrame"] = relationship("DicomFrame", back_populates="annotations")


class DicomAnnotationSession(Base):
    """Tracks which frame a user last annotated (Phase 12c)."""

    __tablename__ = "dicom_annotation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    study_uid: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    series_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    frame_instance_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AnnotationHistory(Base):
    """Undo/audit trail for annotation edits (Phase 12d)."""

    __tablename__ = "annotation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    annotation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dicom_annotations.id"), nullable=True, index=True
    )
    frame_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_frames.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before_state: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="history")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class BackupLog(Base):
    """Record of each backup attempt (Phase 8)."""

    __tablename__ = "backup_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    backup_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # full | db | storage
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|completed|failed
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contains_db: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contains_storage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contains_config: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
