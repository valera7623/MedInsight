"""Optional secrets backend (Vault / cloud KMS)."""

from __future__ import annotations

import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)


def get_secret(name: str, default: str = "") -> str:
    """Resolve secret from Vault when configured, else environment/settings."""
    if settings.VAULT_ENABLED and settings.VAULT_ADDR and settings.VAULT_TOKEN:
        try:
            import httpx

            path = f"{settings.VAULT_ADDR.rstrip('/')}/v1/{settings.VAULT_SECRET_PATH}/{name}"
            resp = httpx.get(path, headers={"X-Vault-Token": settings.VAULT_TOKEN}, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("data", {})
                if name in data:
                    return str(data[name])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vault secret fetch failed for %s: %s", name, exc)
    return os.environ.get(name.upper(), default)
