"""Request-logging middleware.

Assigns/propagates a correlation id (``X-Request-ID``), binds request context
for structlog, and emits one structured line per request with method, path,
status, duration and client info. Unhandled exceptions are logged with a full
stack trace and re-raised so FastAPI's error handling still applies.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.utils.logging import get_logger
from app.utils.request_context import (
    bind_request_context,
    clear_request_context,
    get_user_id,
)

logger = get_logger("app.middleware.logging")

CORRELATION_ID_HEADER = "X-Request-ID"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None


def _extract_identity(request: Request) -> tuple[int | None, int | None]:
    """Best-effort user_id / tenant_id from a Bearer token (no DB hit)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None, None
    try:
        from jose import jwt

        payload = jwt.decode(
            auth.split(" ", 1)[1], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        uid = int(payload["sub"]) if payload.get("sub") else None
        tid = int(payload["tenant_id"]) if payload.get("tenant_id") is not None else None
        return uid, tid
    except Exception:
        return None, None


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_request_context()

        incoming = request.headers.get(CORRELATION_ID_HEADER)
        request_id = incoming or str(uuid.uuid4())

        user_id, tenant_id = (None, None)
        if settings.LOG_INCLUDE_USER_ID:
            user_id, tenant_id = _extract_identity(request)

        bind_request_context(
            request_id=request_id if settings.LOG_INCLUDE_REQUEST_ID else None,
            user_id=user_id,
            tenant_id=tenant_id,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.exception(
                "Request failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                error=str(exc),
            )
            clear_request_context()
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        # A downstream dependency may have resolved the real user; prefer it.
        resolved_user = getattr(getattr(request.state, "user", None), "id", None) or get_user_id()

        response.headers[CORRELATION_ID_HEADER] = request_id

        response_size = response.headers.get("content-length")
        log = logger.bind(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            user_id=resolved_user,
        )
        if response_size is not None:
            try:
                log = log.bind(response_size=int(response_size))
            except ValueError:
                pass

        if response.status_code >= 500:
            log.error("Request completed")
        elif response.status_code >= 400:
            log.warning("Request completed")
        else:
            log.info("Request completed")

        clear_request_context()
        return response
