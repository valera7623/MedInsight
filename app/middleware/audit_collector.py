"""Async audit collection middleware with cryptographic signing."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.database import SessionLocal
from app.middleware.tenant import get_request_tenant_id
from app.models import AuditLog
from app.services.audit_signer import AuditSigner
from app.tasks.audit_export_task import enqueue_pending_batch

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audit-collector")

SKIP_PATHS = re.compile(r"^/(health|static|docs|openapi|login|favicon|help|metrics)")


def _persist_signed_audit(
    *,
    user_id: int | None,
    tenant_id: int | None,
    action: str,
    resource_type: str | None,
    resource_id: int | None,
    ip_address: str | None,
    user_agent: str | None,
    details: dict | None,
) -> None:
    db = SessionLocal()
    try:
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
        db.flush()
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
        if settings.AUDIT_SIGNING_ENABLED:
            entry.signature = AuditSigner.sign_event(event_data)
            entry.signed_at = datetime.utcnow()
        db.commit()
        if settings.SIEM_EXPORT_ENABLED:
            enqueue_pending_batch([entry.id])
    except Exception as exc:
        db.rollback()
        logger.warning("Async audit collector failed: %s", exc)
    finally:
        db.close()


class AuditCollectorMiddleware(BaseHTTPMiddleware):
    """Collect and sign audit events asynchronously (non-blocking)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api/") or SKIP_PATHS.match(request.url.path):
            return response

        from app.middleware.audit import _infer_action, _infer_resource

        action = _infer_action(request.method, request.url.path)
        if not action:
            return response

        user = getattr(request.state, "user", None)
        user_id = user.id if user else None
        tenant_id = get_request_tenant_id(request) or (user.tenant_id if user else None)
        resource_type, resource_id = _infer_resource(request.url.path)

        _executor.submit(
            _persist_signed_audit,
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "collector": "async",
            },
        )
        return response
