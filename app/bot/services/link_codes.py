"""Account linking codes stored in Redis (6-digit, one-time use)."""

from __future__ import annotations

import json
import logging
import secrets

from app.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_LINK_PREFIX = "telegram:link:"


def generate_link_code(
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    first_name: str,
    last_name: str | None,
) -> str | None:
    """Create a 6-digit linking code. Returns None if Redis is unavailable."""
    client = get_redis()
    if client is None:
        logger.warning("Cannot generate Telegram link code — Redis unavailable")
        return None

    payload = {
        "telegram_user_id": telegram_user_id,
        "telegram_username": telegram_username,
        "first_name": first_name,
        "last_name": last_name,
    }

    for _ in range(10):
        code = f"{secrets.randbelow(900_000) + 100_000:06d}"
        key = f"{_LINK_PREFIX}{code}"
        try:
            if client.set(key, json.dumps(payload), nx=True, ex=settings.TELEGRAM_LINK_CODE_TTL):
                return code
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to store Telegram link code: %s", exc)
            return None

    logger.warning("Could not allocate unique Telegram link code")
    return None


def consume_link_code(code: str) -> dict | None:
    """Validate and consume a linking code (one-time)."""
    client = get_redis()
    if client is None:
        return None

    normalized = (code or "").strip()
    if not normalized.isdigit() or len(normalized) != 6:
        return None

    key = f"{_LINK_PREFIX}{normalized}"
    try:
        raw = client.get(key)
        if not raw:
            return None
        client.delete(key)
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to consume Telegram link code: %s", exc)
        return None
