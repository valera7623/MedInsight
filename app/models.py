from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
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
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    department_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="doctor")
    can_see_all_patients: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="users")
    patients: Mapped[list["Patient"]] = relationship(
        "Patient", back_populates="owner", foreign_keys="Patient.user_id"
    )
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="owner")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="owner")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship("AnalysisJob", back_populates="owner")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="discharge")
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parsed_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="documents")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="documents")
    owner: Mapped["User"] = relationship("User", back_populates="documents")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship("AnalysisJob", back_populates="document")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("documents.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prediction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    probabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")
    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="audit_logs")


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
    solution_code: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    events: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
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
