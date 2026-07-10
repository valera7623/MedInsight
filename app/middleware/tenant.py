from __future__ import annotations

from fastapi import Request

from app.config import settings
from app.database import SessionLocal
from app.models import Tenant


def _jwt_payload(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        from jose import jwt

        token = auth.split(" ", 1)[1]
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        return None


def get_request_tenant_id(request: Request) -> int | None:
    """Resolve tenant id for middleware (cache, usage limits).

    JWT tenant is authoritative for regular users. X-Tenant-ID header override
    is allowed only for super_admin.
    """
    if hasattr(request.state, "tenant_id"):
        return request.state.tenant_id

    payload = _jwt_payload(request)
    if payload is not None:
        role = payload.get("role")
        jwt_tid = payload.get("tenant_id")
        header = request.headers.get("X-Tenant-ID")
        if role == "super_admin" and header and header.isdigit():
            request.state.tenant_id = int(header)
            return int(header)
        if jwt_tid is not None:
            request.state.tenant_id = int(jwt_tid)
            return int(jwt_tid)

    header = request.headers.get("X-Tenant-ID")
    if header and header.isdigit():
        request.state.tenant_id = int(header)
        return int(header)

    subdomain = request.headers.get("X-Tenant-Subdomain")
    if subdomain:
        db = SessionLocal()
        try:
            tenant = db.query(Tenant).filter(Tenant.subdomain == subdomain, Tenant.is_active.is_(True)).first()
            if tenant:
                request.state.tenant_id = tenant.id
                return tenant.id
        finally:
            db.close()

    return None
