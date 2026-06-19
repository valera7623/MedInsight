import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.database import SessionLocal
from app.middleware.tenant import get_request_tenant_id
from app.services.audit import log_audit

logger = logging.getLogger(__name__)

AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_PATHS = re.compile(r"^/(health|static|docs|openapi|login|favicon)")


ACTION_MAP = {
    ("POST", "/api/auth/login"): "login",
    ("POST", "/api/documents/upload"): "upload",
    ("POST", "/api/export"): "export",
    ("POST", "/api/analytics/predict"): "predict",
    ("DELETE", "/api/patients"): "delete",
    ("DELETE", "/api/admin/tenants"): "delete",
}


def _infer_action(method: str, path: str) -> str | None:
    if method == "GET" and "/download" in path:
        return "download"
    if method == "GET" and path.startswith("/api/"):
        return "view"
    for (m, prefix), action in ACTION_MAP.items():
        if method == m and path.startswith(prefix):
            return action
    if method in AUDITED_METHODS:
        return method.lower()
    return None


def _infer_resource(path: str) -> tuple[str | None, int | None]:
    parts = [p for p in path.split("/") if p.isdigit()]
    if "/patients/" in path:
        return "patient", int(parts[0]) if parts else None
    if "/documents/" in path:
        return "document", int(parts[0]) if parts else None
    if "/predictions/" in path or "/predict/" in path:
        return "prediction", int(parts[0]) if parts else None
    if "/users/" in path:
        return "user", int(parts[0]) if parts else None
    if "/tenants/" in path:
        return "tenant", int(parts[0]) if parts else None
    return None, None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        if SKIP_PATHS.match(path) or not path.startswith("/api/"):
            return response

        action = _infer_action(request.method, path)
        if not action:
            return response

        user = getattr(request.state, "user", None)
        user_id = user.id if user else None
        tenant_id = get_request_tenant_id(request) or (user.tenant_id if user else None)

        if user_id is None:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                try:
                    from jose import jwt
                    from app.config import settings as cfg

                    payload = jwt.decode(auth.split(" ", 1)[1], cfg.SECRET_KEY, algorithms=[cfg.ALGORITHM])
                    user_id = int(payload["sub"]) if payload.get("sub") else None
                    if tenant_id is None and payload.get("tenant_id") is not None:
                        tenant_id = int(payload["tenant_id"])
                except Exception:
                    pass
        resource_type, resource_id = _infer_resource(path)

        db = SessionLocal()
        try:
            log_audit(
                db,
                user_id=user_id,
                tenant_id=tenant_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                details={"method": request.method, "path": path, "status": response.status_code},
            )
        finally:
            db.close()

        return response
