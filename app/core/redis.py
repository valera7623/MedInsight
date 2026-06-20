"""Shared synchronous Redis client.

A single lazily-created connection pool is reused across the app (rate limiting,
health checks, etc.). All access is defensive: if Redis is unreachable callers
get ``None`` / ``False`` instead of an exception, so the API keeps working.
"""

from __future__ import annotations

import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    """Return a shared Redis client, or ``None`` if Redis cannot be reached."""
    global _client
    if _client is not None:
        return _client
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        client.ping()
        _client = client
        logger.info("Redis client connected: %s", settings.REDIS_URL)
        return _client
    except Exception as exc:  # noqa: BLE001 — never let Redis break the request path
        logger.warning("Redis unavailable (%s)", exc)
        return None


def ping_redis() -> bool:
    """Lightweight reachability check used by the readiness probe."""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis ping failed (%s)", exc)
        return False


def close_redis_connection() -> None:
    """Close the shared Redis connection pool (used during graceful shutdown)."""
    global _client
    if _client is None:
        logger.info("Redis: no active connection to close")
        return
    try:
        _client.close()
        try:
            _client.connection_pool.disconnect()
        except Exception:  # noqa: BLE001
            pass
        logger.info("Redis connection closed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error closing Redis connection: %s", exc)
    finally:
        _client = None
