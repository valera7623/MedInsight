"""Server-side refresh token / session registry (Redis)."""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any

from app.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

SESSION_PREFIX = "session:"
USER_SESSIONS_PREFIX = "user_sessions:"


def _session_key(jti: str) -> str:
    return f"{SESSION_PREFIX}{jti}"


def _user_sessions_key(user_id: int) -> str:
    return f"{USER_SESSIONS_PREFIX}{user_id}"


def create_session(
    user_id: int,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    jti = secrets.token_urlsafe(32)
    if not settings.SESSION_STORE_ENABLED:
        return jti
    client = get_redis()
    if client is None:
        return jti
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    payload = {
        "user_id": user_id,
        "created_at": int(time.time()),
        "user_agent": (user_agent or "")[:512],
        "ip_address": ip_address or "",
    }
    try:
        pipe = client.pipeline()
        pipe.setex(_session_key(jti), ttl, json.dumps(payload))
        pipe.sadd(_user_sessions_key(user_id), jti)
        pipe.expire(_user_sessions_key(user_id), ttl)
        pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session create failed: %s", exc)
    return jti


def session_valid(jti: str, user_id: int) -> bool:
    if not settings.SESSION_STORE_ENABLED:
        return True
    client = get_redis()
    if client is None:
        return True
    try:
        raw = client.get(_session_key(jti))
        if not raw:
            return False
        data = json.loads(raw)
        return int(data.get("user_id", -1)) == user_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session validate failed: %s", exc)
        return True


def revoke_session(jti: str, user_id: int) -> None:
    if not settings.SESSION_STORE_ENABLED:
        return
    client = get_redis()
    if client is None:
        return
    try:
        pipe = client.pipeline()
        pipe.delete(_session_key(jti))
        pipe.srem(_user_sessions_key(user_id), jti)
        pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session revoke failed: %s", exc)


def revoke_all_sessions(user_id: int) -> int:
    if not settings.SESSION_STORE_ENABLED:
        return 0
    client = get_redis()
    if client is None:
        return 0
    try:
        jtis = client.smembers(_user_sessions_key(user_id)) or set()
        count = 0
        for jti in jtis:
            jti_str = jti.decode() if isinstance(jti, bytes) else str(jti)
            client.delete(_session_key(jti_str))
            count += 1
        client.delete(_user_sessions_key(user_id))
        return count
    except Exception as exc:  # noqa: BLE001
        logger.warning("Revoke all sessions failed: %s", exc)
        return 0


def list_sessions(user_id: int) -> list[dict[str, Any]]:
    client = get_redis()
    if client is None or not settings.SESSION_STORE_ENABLED:
        return []
    out: list[dict[str, Any]] = []
    try:
        jtis = client.smembers(_user_sessions_key(user_id)) or set()
        for jti in jtis:
            jti_str = jti.decode() if isinstance(jti, bytes) else str(jti)
            raw = client.get(_session_key(jti_str))
            if not raw:
                continue
            data = json.loads(raw)
            data["jti"] = jti_str
            out.append(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("List sessions failed: %s", exc)
    return sorted(out, key=lambda x: x.get("created_at", 0), reverse=True)
