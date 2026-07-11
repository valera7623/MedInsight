"""Tenant MFA policy enforcement."""

from __future__ import annotations

from app.config import settings
from app.models import Tenant, User


def _parse_role_list(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def tenant_mfa_required_roles(tenant: Tenant | None) -> set[str]:
    if tenant and isinstance(tenant.settings, dict):
        roles = tenant.settings.get("mfa_required_roles")
        if isinstance(roles, list):
            return {str(r) for r in roles}
    return _parse_role_list(settings.MFA_REQUIRED_ROLES)


def mfa_required_for_user(user: User, tenant: Tenant | None) -> bool:
    if not settings.MFA_ENFORCED:
        return False
    if user.role == "super_admin" and settings.ENVIRONMENT == "production":
        return True
    return user.role in tenant_mfa_required_roles(tenant)


def assert_mfa_compliance(user: User, tenant: Tenant | None) -> None:
    if mfa_required_for_user(user, tenant) and not user.totp_enabled:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="2FA is required for your role. Enable TOTP in account settings.",
        )
