"""Remove a tenant and dependent data while preserving append-only audit history."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AnalysisJob,
    Appointment,
    AppointmentHistory,
    AppointmentRecurring,
    AppointmentType,
    Department,
    ErrorFix,
    Patient,
    Payment,
    Prediction,
    ReportTemplate,
    ReportTemplateVariable,
    Subscription,
    Tenant,
    User,
    UserPreference,
    Webhook,
)
from app.services.patient_deletion import delete_patient_with_dependencies

logger = logging.getLogger(__name__)


def _detach_audit_logs(db: Session, tenant_id: int) -> None:
    """Keep audit rows but drop tenant FK (append-only table forbids DELETE)."""
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER trg_audit_logs_append_only"))
    try:
        db.execute(
            text("UPDATE audit_logs SET tenant_id = NULL WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
    finally:
        if bind.dialect.name == "postgresql":
            db.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_append_only"))


def delete_tenant_with_dependencies(db: Session, tenant: Tenant) -> None:
    """Hard-delete tenant data. Audit log rows are retained with tenant_id cleared."""
    tenant_id = tenant.id

    for patient in db.query(Patient).filter(Patient.tenant_id == tenant_id).all():
        delete_patient_with_dependencies(db, patient)

    db.query(Prediction).filter(Prediction.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(AnalysisJob).filter(AnalysisJob.tenant_id == tenant_id).delete(synchronize_session=False)

    template_ids = [
        row[0]
        for row in db.query(ReportTemplate.id).filter(ReportTemplate.tenant_id == tenant_id).all()
    ]
    if template_ids:
        db.query(ReportTemplateVariable).filter(
            ReportTemplateVariable.template_id.in_(template_ids)
        ).delete(synchronize_session=False)
    db.query(ReportTemplate).filter(ReportTemplate.tenant_id == tenant_id).delete(synchronize_session=False)

    appt_ids = [row[0] for row in db.query(Appointment.id).filter(Appointment.tenant_id == tenant_id).all()]
    if appt_ids:
        db.query(AppointmentHistory).filter(AppointmentHistory.appointment_id.in_(appt_ids)).delete(
            synchronize_session=False
        )
        db.query(AppointmentRecurring).filter(AppointmentRecurring.appointment_id.in_(appt_ids)).delete(
            synchronize_session=False
        )
    db.query(Appointment).filter(Appointment.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(AppointmentType).filter(AppointmentType.tenant_id == tenant_id).delete(synchronize_session=False)

    db.query(Webhook).filter(Webhook.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Payment).filter(Payment.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Subscription).filter(Subscription.tenant_id == tenant_id).delete(synchronize_session=False)

    user_ids = [row[0] for row in db.query(User.id).filter(User.tenant_id == tenant_id).all()]
    if user_ids:
        db.query(UserPreference).filter(UserPreference.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tenant_id).delete(synchronize_session=False)

    db.query(Department).filter(Department.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(ErrorFix).filter(ErrorFix.tenant_id == tenant_id).update(
        {ErrorFix.tenant_id: None}, synchronize_session=False
    )

    _detach_audit_logs(db, tenant_id)

    db.delete(tenant)
    db.commit()

    enc_dir = Path(settings.STORAGE_PATH) / "encrypted" / f"tenant_{tenant_id}"
    if enc_dir.exists():
        shutil.rmtree(enc_dir, ignore_errors=True)
