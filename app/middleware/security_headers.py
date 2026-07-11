"""Security headers middleware (enterprise hardening)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if not settings.SECURITY_HEADERS_ENABLED:
            return response
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if settings.SECURITY_HSTS_ENABLED:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.SECURITY_HSTS_MAX_AGE}; includeSubDomains",
            )
        if settings.SECURITY_CSP:
            response.headers.setdefault("Content-Security-Policy", settings.SECURITY_CSP)
        return response
