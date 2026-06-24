"""Append-only protection for audit_logs — block UPDATE and DELETE."""

from __future__ import annotations

import logging

from sqlalchemy import event, inspect
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog

logger = logging.getLogger(__name__)

_APPEND_ONLY_MSG = "audit_logs is append-only: UPDATE and DELETE are forbidden"


@event.listens_for(AuditLog, "before_update", propagate=True)
def _block_audit_update(_mapper, _connection, target: AuditLog) -> None:
    allowed = {
        "signature",
        "signed_at",
        "export_status",
        "export_attempts",
        "last_export_attempt_at",
        "export_error",
    }
    insp = inspect(target)
    changed = {attr.key for attr in insp.attrs if attr.history.has_changes()}
    forbidden = changed - allowed
    if forbidden:
        logger.warning("Blocked audit_logs UPDATE on fields: %s", forbidden)
        raise IntegrityError(_APPEND_ONLY_MSG, params=None, orig=None)


@event.listens_for(AuditLog, "before_delete", propagate=True)
def _block_audit_delete(_mapper, _connection, _target: AuditLog) -> None:
    logger.warning("Blocked audit_logs DELETE")
    raise IntegrityError(_APPEND_ONLY_MSG, params=None, orig=None)


def register_append_only_listeners() -> None:
    """Import side-effect registers listeners; call at app startup for clarity."""
    logger.debug("Audit append-only listeners registered")
