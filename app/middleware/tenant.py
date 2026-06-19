from fastapi import Request

from app.config import settings
from app.database import SessionLocal
from app.models import Tenant


def get_request_tenant_id(request: Request) -> int | None:
    if hasattr(request.state, "tenant_id"):
        return request.state.tenant_id

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

    if settings.TENANT_MODE:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                from jose import jwt
                from app.config import settings as cfg

                token = auth.split(" ", 1)[1]
                payload = jwt.decode(token, cfg.SECRET_KEY, algorithms=[cfg.ALGORITHM])
                tid = payload.get("tenant_id")
                if tid is not None:
                    request.state.tenant_id = int(tid)
                    return int(tid)
            except Exception:
                pass

    return None
