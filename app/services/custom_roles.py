"""Per-tenant custom roles (ABAC-lite)."""

from __future__ import annotations

from app.config import settings
from app.models import Tenant


def custom_roles_enabled(tenant: Tenant | None) -> bool:
    if not settings.CUSTOM_ROLES_ENABLED:
        return False
    if tenant and isinstance(tenant.settings, dict):
        return bool(tenant.settings.get("custom_roles_enabled"))
    return False


def tenant_permissions(tenant: Tenant | None) -> dict[str, list[str]]:
    if not tenant or not isinstance(tenant.settings, dict):
        return {}
    perms = tenant.settings.get("role_permissions")
    return perms if isinstance(perms, dict) else {}
