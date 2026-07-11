import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog
from app.services.audit_signer import AuditSigner
from app.tasks.audit_export_task import enqueue_pending_batch

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    *,
    user_id: int | None,
    tenant_id: int | None,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict | None = None,
) -> AuditLog | None:
    entry = AuditLog(
        user_id=user_id,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        export_status="pending",
    )
    db.add(entry)
    try:
        db.flush()
        if settings.AUDIT_SIGNING_ENABLED:
            event_data = {
                "id": entry.id,
                "user_id": entry.user_id,
                "tenant_id": entry.tenant_id,
                "action": entry.action,
                "resource_type": entry.resource_type,
                "resource_id": entry.resource_id,
                "ip_address": entry.ip_address,
                "user_agent": entry.user_agent,
                "details": entry.details,
                "created_at": entry.created_at or datetime.utcnow(),
            }
            entry.signature = AuditSigner.sign_event(event_data)
            entry.signed_at = datetime.utcnow()
        db.commit()
        if settings.SIEM_EXPORT_ENABLED:
            enqueue_pending_batch([entry.id])
        if settings.SIEM_WEBHOOK_ENABLED:
            from app.services.siem_webhook import push_audit_event

            push_audit_event(
                {
                    "id": entry.id,
                    "action": entry.action,
                    "tenant_id": entry.tenant_id,
                    "user_id": entry.user_id,
                    "resource_type": entry.resource_type,
                    "resource_id": entry.resource_id,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                }
            )
        return entry
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to write audit log: %s", exc)
        return None
