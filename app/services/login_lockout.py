"""Per-account login lockout (Redis-backed)."""

from __future__ import annotations

import logging
import time

from app.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def _fail_key(user_id: int) -> str:
    return f"login_fail:{user_id}"


def _lock_key(user_id: int) -> str:
    return f"login_lock:{user_id}"


def is_locked(user_id: int) -> tuple[bool, int]:
    client = get_redis()
    if client is None:
        return False, 0
    try:
        ttl = client.ttl(_lock_key(user_id))
        if ttl and ttl > 0:
            return True, int(ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lockout check failed: %s", exc)
    return False, 0


def record_failed_login(user_id: int) -> tuple[int, bool]:
    """Increment failures; lock if threshold exceeded. Returns (fail_count, now_locked)."""
    client = get_redis()
    if client is None:
        return 0, False
    max_attempts = settings.LOGIN_LOCKOUT_MAX_ATTEMPTS
    lock_seconds = settings.LOGIN_LOCKOUT_DURATION_SECONDS
    try:
        fails = int(client.incr(_fail_key(user_id)))
        client.expire(_fail_key(user_id), lock_seconds)
        if fails >= max_attempts:
            client.setex(_lock_key(user_id), lock_seconds, str(int(time.time())))
            client.delete(_fail_key(user_id))
            return fails, True
        return fails, False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lockout record failed: %s", exc)
        return 0, False


def clear_failed_logins(user_id: int) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(_fail_key(user_id), _lock_key(user_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lockout clear failed: %s", exc)
