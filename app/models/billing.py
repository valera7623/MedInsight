"""ORM models — billing."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.db.types import PortableJSON, PortableTSVector, PortableUUID, uuid_default
from app.models._time import utc_now


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    # SIEM export & signing (Phase 13)
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # server_default required: PG audit_log_trigger inserts without this column.
    export_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    event: Mapped["AuditLog"] = relationship("AuditLog", back_populates="export_logs")

class AuditKey(Base):
    """Encrypted signing key for audit event integrity."""

    __tablename__ = "audit_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    events: Mapped[list | None] = mapped_column(PortableJSON, nullable=True, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
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
    current_period_start: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class CacheVersion(Base):
    """Logical cache version for invalidation without scanning all Redis keys."""

    __tablename__ = "cache_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cache_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

class CacheStats(Base):
    """Access statistics for Redis/static cache entries."""

    __tablename__ = "cache_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cache_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

