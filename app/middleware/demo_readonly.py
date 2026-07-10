"""Block mutating API requests when DEMO_MODE is enabled."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Auth and health must remain usable in the public demo.
# Export/report generation is read-only from a data perspective (writes temp files only).
_ALLOWED_PREFIXES = (
    "/api/auth/login",
    "/api/auth/request-reset",
    "/api/auth/resend-verification",
    "/api/auth/verify-email",
    "/api/export/",
    "/api/reports/generate",
    "/api/reports/preview",
    "/health",
    "/metrics",
)


class DemoReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject write operations in the buyer-facing demo stack."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.DEMO_MODE:
            return await call_next(request)

        if request.method not in _MUTATING:
            return await call_next(request)

        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _ALLOWED_PREFIXES):
            return await call_next(request)
        # Exact match for login without trailing slash variants already covered.
        if path.rstrip("/") in {p.rstrip("/") for p in _ALLOWED_PREFIXES}:
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={
                "detail": "В демо-версии изменение данных недоступно. Доступен только просмотр.",
            },
        )
