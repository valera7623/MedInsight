"""Enterprise SSO (OIDC) routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_access_token, create_refresh_token, user_to_response
from app.config import settings
from app.core.redis import get_redis
from app.database import get_db
from app.models import User
from app.services.audit import log_audit
from app.services.session_store import create_session
from app.services.sso.oidc import (
    authorization_url,
    decode_id_token,
    exchange_code,
    new_state,
    sso_enabled,
)

router = APIRouter(prefix="/auth/sso", tags=["sso"])

STATE_PREFIX = "sso_state:"
STATE_TTL = 600


class SsoStatusResponse(BaseModel):
    enabled: bool
    provider: str | None = None


def _store_state(state: str) -> None:
    client = get_redis()
    if client:
        client.setex(f"{STATE_PREFIX}{state}", STATE_TTL, "1")


def _consume_state(state: str) -> bool:
    client = get_redis()
    if not client:
        return True
    key = f"{STATE_PREFIX}{state}"
    if not client.get(key):
        return False
    client.delete(key)
    return True


@router.get("/status", response_model=SsoStatusResponse)
def sso_status():
    return SsoStatusResponse(
        enabled=sso_enabled(),
        provider="oidc" if sso_enabled() else None,
    )


@router.get("/login")
async def sso_login():
    if not sso_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO not configured")
    state = new_state()
    _store_state(state)
    return RedirectResponse(authorization_url(state))


@router.get("/callback")
async def sso_callback(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    code: str = Query(...),
    state: str = Query(...),
):
    if not sso_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO not configured")
    if not _consume_state(state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid SSO state")

    token_data = await exchange_code(code)
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing id_token")
    claims = decode_id_token(id_token)
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email claim required")

    user = db.query(User).filter(User.email == email).first()
    if not user or user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not provisioned for SSO")

    jti = create_session(
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    from app.auth import create_refresh_token_with_jti

    refresh = create_refresh_token_with_jti(user, jti)
    access = create_access_token(user)

    log_audit(
        db,
        user_id=user.id,
        tenant_id=user.tenant_id,
        action="auth.login_sso",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    frontend = settings.FRONTEND_URL.rstrip("/")
    return RedirectResponse(
        f"{frontend}/login?sso=1&access_token={access}&refresh_token={refresh}"
    )
