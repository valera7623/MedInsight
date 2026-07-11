"""Field-level PHI encryption helpers."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet | None:
    if not settings.PHI_FIELD_ENCRYPTION_ENABLED:
        return None
    key = settings.PHI_FIELD_ENCRYPTION_KEY or settings.SECRET_KEY
    digest = hashlib.sha256(key.encode()).digest()
    fkey = base64.urlsafe_b64encode(digest)
    return Fernet(fkey)


def encrypt_field(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    f = _fernet()
    if f is None:
        return value
    token = f.encrypt(value.encode("utf-8"))
    return "enc:" + token.decode("ascii")


def decrypt_field(value: str | None) -> str | None:
    if value is None or not str(value).startswith("enc:"):
        return value
    f = _fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value[4:].encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.warning("PHI field decrypt failed")
        return value
