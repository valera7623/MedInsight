"""Redis-backed sliding-window rate limiting.

Provides a ``@rate_limit(limit=..., period=...)`` decorator for FastAPI route
handlers. Counting uses a Redis sorted set per ``rate_limit:{ip}:{endpoint}``
key: each request is recorded with its timestamp, stale entries are trimmed, and
the cardinality of the window is compared against the limit. This yields a true
rolling window (not a fixed bucket that resets on a clock boundary).

Fail-open: if Redis is unreachable or rate limiting is disabled, requests are
allowed through so an infrastructure hiccup never locks users out.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import time
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, status

from app.config import settings
from app.core.metrics import rate_limit_exceeded_total
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """Resolve the real client IP, honouring a reverse proxy (Traefik/nginx)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _ip_hash(ip: str) -> str:
    """Short, non-reversible IP fingerprint for metric labels (privacy + cardinality)."""
    return hashlib.sha256(ip.encode()).hexdigest()[:12]


def _find_request(args: tuple, kwargs: dict) -> Request | None:
    candidate = kwargs.get("request")
    if isinstance(candidate, Request):
        return candidate
    for value in args:
        if isinstance(value, Request):
            return value
    for value in kwargs.values():
        if isinstance(value, Request):
            return value
    return None


def check_rate_limit(ip: str, endpoint: str, limit: int, period: int) -> tuple[bool, int]:
    """Record a hit and report whether it is allowed.

    Returns ``(allowed, retry_after_seconds)``. Fails open when Redis is down.
    """
    client = get_redis()
    if client is None:
        return True, 0

    key = f"rate_limit:{ip}:{endpoint}"
    now = time.time()
    window_start = now - period

    try:
        pipe = client.pipeline()
        # Drop entries that fell out of the rolling window.
        pipe.zremrangebyscore(key, 0, window_start)
        # Record this request (unique member so identical timestamps don't collide).
        pipe.zadd(key, {f"{now}:{int(now * 1_000_000) % 1_000_000}": now})
        pipe.zcard(key)
        pipe.expire(key, period)
        results = pipe.execute()
        count = int(results[2])
    except Exception as exc:  # noqa: BLE001 — never block traffic on a Redis error
        logger.warning("Rate limit check failed for %s (%s) — allowing", key, exc)
        return True, 0

    if count > limit:
        # Compute when the oldest in-window hit expires → Retry-After.
        try:
            oldest = client.zrange(key, 0, 0, withscores=True)
            retry_after = period
            if oldest:
                retry_after = max(1, int(oldest[0][1] + period - now))
        except Exception:  # noqa: BLE001
            retry_after = period
        return False, retry_after

    return True, 0


def rate_limit(limit: int, period: int, name: str | None = None):
    """Decorator enforcing ``limit`` requests per ``period`` seconds per client IP.

    The wrapped handler must declare a ``request: Request`` parameter so the
    client IP can be resolved. Works on both ``async def`` and ``def`` handlers.
    """

    def decorator(func: Callable):
        endpoint = name or func.__name__

        def _enforce(request: Request | None) -> None:
            if not settings.RATE_LIMIT_ENABLED:
                return
            if request is None:
                logger.warning(
                    "Rate limit on %s skipped: no Request argument found", endpoint
                )
                return
            ip = _client_ip(request)
            allowed, retry_after = check_rate_limit(ip, endpoint, limit, period)
            if not allowed:
                rate_limit_exceeded_total.labels(endpoint=endpoint, ip_hash=_ip_hash(ip)).inc()
                logger.warning(
                    "Rate limit exceeded: ip=%s endpoint=%s (limit=%d/%ds)",
                    ip,
                    endpoint,
                    limit,
                    period,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too Many Requests. Retry after {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )

        if _is_coroutine(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                _enforce(_find_request(args, kwargs))
                return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _enforce(_find_request(args, kwargs))
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator


def _is_coroutine(func: Callable) -> bool:
    import asyncio

    return asyncio.iscoroutinefunction(func)
