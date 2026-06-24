"""Audit key management and archive signing."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditKey
from app.services.encryption import _decrypt_bytes, _encrypt_bytes

logger = logging.getLogger(__name__)


class CryptoAudit:
    """Manage audit signing keys and archive signatures."""

    @staticmethod
    def generate_audit_key() -> str:
        key_path = Path(settings.AUDIT_SIGNING_KEY_PATH)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            return key_path.read_text(encoding="utf-8").strip()
        raw = secrets.token_hex(32)
        key_path.write_text(raw, encoding="utf-8")
        key_path.chmod(0o600)
        logger.info("Generated audit signing key at %s", key_path)
        return raw

    @staticmethod
    def _encrypt_key_for_storage(raw_key: str) -> str:
        import base64

        return base64.b64encode(_encrypt_bytes(raw_key.encode("utf-8"))).decode("ascii")

    @staticmethod
    def _decrypt_key_from_storage(stored: str) -> str:
        import base64

        return _decrypt_bytes(base64.b64decode(stored.encode("ascii"))).decode("utf-8")

    @classmethod
    def store_key_in_db(cls, db: Session, *, expires_days: int | None = None) -> AuditKey:
        raw = cls.generate_audit_key()
        expires_at = None
        if expires_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_days)
        db.query(AuditKey).filter(AuditKey.active.is_(True)).update({"active": False})
        record = AuditKey(
            key=cls._encrypt_key_for_storage(raw),
            active=True,
            expires_at=expires_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @classmethod
    def rotate_audit_key(cls, db: Session | None = None) -> None:
        from app.database import SessionLocal

        owns_session = db is None
        db = db or SessionLocal()
        try:
            cls.store_key_in_db(db)
            logger.info("Audit signing key rotated")
        finally:
            if owns_session:
                db.close()

    @classmethod
    def sign_archive(cls, archive_path: str) -> str:
        path = Path(archive_path)
        if not path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")
        key = Path(settings.AUDIT_SIGNING_KEY_PATH)
        secret = key.read_bytes() if key.exists() else cls.generate_audit_key().encode("utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return hmac.new(secret, digest.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def verify_archive(cls, archive_path: str, signature: str) -> bool:
        if not signature:
            return False
        try:
            expected = cls.sign_archive(archive_path)
            return hmac.compare_digest(expected, signature)
        except FileNotFoundError:
            return False
