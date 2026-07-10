"""TOTP two-factor authentication helpers."""

from __future__ import annotations

import json
import secrets

import pyotp

from app.config import settings


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.APP_NAME if hasattr(settings, "APP_NAME") else "MedInsight")


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_backup_codes(count: int = 8) -> list[str]:
    return [secrets.token_hex(4) for _ in range(count)]


def backup_codes_to_json(codes: list[str]) -> str:
    return json.dumps(codes)


def backup_codes_from_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(c) for c in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def consume_backup_code(stored_json: str | None, code: str) -> tuple[bool, str | None]:
    codes = backup_codes_from_json(stored_json)
    normalized = code.strip().lower()
    for i, c in enumerate(codes):
        if c.lower() == normalized:
            codes.pop(i)
            return True, backup_codes_to_json(codes)
    return False, stored_json
