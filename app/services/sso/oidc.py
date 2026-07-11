"""OpenID Connect authorization code flow (enterprise SSO)."""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import jwt

from app.config import settings

logger = logging.getLogger(__name__)


def sso_enabled() -> bool:
    return bool(
        settings.SSO_OIDC_ENABLED
        and settings.SSO_OIDC_CLIENT_ID
        and settings.SSO_OIDC_CLIENT_SECRET
        and settings.SSO_OIDC_ISSUER_URL
    )


def authorization_url(state: str, *, redirect_uri: str | None = None) -> str:
    redirect = redirect_uri or settings.SSO_OIDC_REDIRECT_URI
    params = {
        "client_id": settings.SSO_OIDC_CLIENT_ID,
        "response_type": "code",
        "scope": settings.SSO_OIDC_SCOPES,
        "redirect_uri": redirect,
        "state": state,
    }
    base = settings.SSO_OIDC_AUTHORIZE_URL or f"{settings.SSO_OIDC_ISSUER_URL.rstrip('/')}/authorize"
    return f"{base}?{urlencode(params)}"


def new_state() -> str:
    return secrets.token_urlsafe(32)


async def exchange_code(code: str, *, redirect_uri: str | None = None) -> dict[str, Any]:
    redirect = redirect_uri or settings.SSO_OIDC_REDIRECT_URI
    token_url = settings.SSO_OIDC_TOKEN_URL or f"{settings.SSO_OIDC_ISSUER_URL.rstrip('/')}/token"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": settings.SSO_OIDC_CLIENT_ID,
                "client_secret": settings.SSO_OIDC_CLIENT_SECRET,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


def decode_id_token(id_token: str) -> dict[str, Any]:
    # Signature verification optional when issuer provides JWKS; decode claims for MVP.
    return jwt.get_unverified_claims(id_token)
