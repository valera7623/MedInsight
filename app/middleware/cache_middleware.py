"""HTTP middleware: cache GET JSON responses for configured API paths."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.core.cache import CacheService, cache_enabled

logger = logging.getLogger(__name__)

# path prefix -> TTL seconds
DEFAULT_CACHE_RULES: dict[str, int] = {
    "/api/patients": settings.REDIS_CACHE_API_TTL,
    "/api/analytics/dashboard": settings.REDIS_CACHE_API_TTL,
    "/api/dicom/studies": settings.REDIS_CACHE_API_TTL,
}


def _match_rule(path: str) -> int | None:
    for prefix, ttl in DEFAULT_CACHE_RULES.items():
        if path == prefix or path.startswith(prefix + "/"):
            return ttl
    return None


def _request_cache_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    auth_hash = hashlib.sha256(auth.encode()).hexdigest()[:12] if auth else "anon"
    query = request.url.query
    return f"http_cache:{request.method}:{request.url.path}?{query}:auth:{auth_hash}"


class CacheMiddleware(BaseHTTPMiddleware):
    """Cache successful GET responses for whitelisted API paths."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not cache_enabled() or request.method != "GET":
            return await call_next(request)

        ttl = _match_rule(request.url.path)
        if ttl is None:
            return await call_next(request)

        cache_key = _request_cache_key(request)
        cached = await CacheService.get(cache_key)
        if cached is not None:
            try:
                payload = json.loads(cached.decode("utf-8"))
                return Response(
                    content=payload["body"],
                    status_code=payload["status"],
                    media_type=payload.get("media_type", "application/json"),
                    headers={"X-Cache": "HIT"},
                )
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError):
                await CacheService.delete(cache_key)

        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if response.status_code != 200 or "application/json" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        await CacheService.set(
            cache_key,
            json.dumps(
                {
                    "status": response.status_code,
                    "body": body.decode("utf-8"),
                    "media_type": content_type.split(";")[0],
                }
            ).encode("utf-8"),
            ttl=ttl,
        )

        return Response(
            content=body,
            status_code=response.status_code,
            media_type=content_type,
            headers={**dict(response.headers), "X-Cache": "MISS"},
        )
