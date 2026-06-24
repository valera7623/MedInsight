"""Cryptographic signing and verification for audit events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_SIGNING_FIELDS = (
    "id",
    "user_id",
    "tenant_id",
    "action",
    "resource_type",
    "resource_id",
    "ip_address",
    "user_agent",
    "details",
    "created_at",
)


def _load_signing_key() -> bytes:
    from pathlib import Path

    from app.services.crypto_audit import CryptoAudit

    key_path = Path(settings.AUDIT_SIGNING_KEY_PATH)
    if key_path.exists():
        return key_path.read_bytes()
    return CryptoAudit.generate_audit_key().encode("utf-8")


class AuditSigner:
    """HMAC-SHA256 signing for audit event integrity."""

    @staticmethod
    def normalize_event_data(event_data: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for field in _SIGNING_FIELDS:
            value = event_data.get(field)
            if isinstance(value, datetime):
                normalized[field] = value.isoformat()
            elif value is None:
                normalized[field] = None
            else:
                normalized[field] = value
        return normalized

    @classmethod
    def get_event_hash(cls, event_data: dict[str, Any]) -> str:
        payload = json.dumps(
            cls.normalize_event_data(event_data),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def sign_event(cls, event_data: dict[str, Any]) -> str:
        if not settings.AUDIT_SIGNING_ENABLED:
            return cls.get_event_hash(event_data)
        key = _load_signing_key()
        digest = cls.get_event_hash(event_data)
        return hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(cls, event_data: dict[str, Any], signature: str) -> bool:
        if not signature:
            return False
        if not settings.AUDIT_SIGNING_ENABLED:
            return hmac.compare_digest(cls.get_event_hash(event_data), signature)
        key = _load_signing_key()
        digest = cls.get_event_hash(event_data)
        expected = hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
