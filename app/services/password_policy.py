"""Enterprise password policy validation."""

from __future__ import annotations

import hashlib
import re

import httpx

from app.config import settings

_COMPLEXITY_RE = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$"
)


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str, *, email: str | None = None) -> None:
    min_len = settings.PASSWORD_MIN_LENGTH
    if len(password) < min_len:
        raise PasswordPolicyError(f"Password must be at least {min_len} characters")

    if settings.PASSWORD_REQUIRE_COMPLEXITY and not _COMPLEXITY_RE.match(password):
        raise PasswordPolicyError(
            "Password must include upper and lower case, a digit, and a special character"
        )

    if email and password.lower() == email.lower():
        raise PasswordPolicyError("Password must not match email")

    if settings.PASSWORD_HIBP_CHECK_ENABLED:
        if _is_breached(password):
            raise PasswordPolicyError("Password appears in a known breach; choose another")


def _is_breached(password: str) -> bool:
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"https://api.pwnedpasswords.com/range/{prefix}")
        if resp.status_code != 200:
            return False
        for line in resp.text.splitlines():
            part, _count = line.split(":", 1)
            if part == suffix:
                return True
    except Exception:
        return False
    return False
