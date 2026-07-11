"""WebAuthn / FIDO2 registration and authentication (enterprise)."""

from __future__ import annotations

from app.config import settings


def webauthn_enabled() -> bool:
    return bool(settings.WEBAUTHN_ENABLED and settings.WEBAUTHN_RP_ID)
