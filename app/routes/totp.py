"""TOTP 2FA setup and management routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import bump_token_version, get_current_user, verify_password
from app.database import get_db
from app.models import User
from app.services.totp import (
    backup_codes_to_json,
    consume_backup_code,
    generate_backup_codes,
    generate_totp_secret,
    totp_provisioning_uri,
    verify_totp,
)

router = APIRouter(prefix="/auth/totp", tags=["totp"])


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    backup_codes: list[str]


class TotpCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TotpDisableRequest(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=8)


@router.get("/setup", response_model=TotpSetupResponse)
def totp_setup(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    secret = generate_totp_secret()
    backup = generate_backup_codes()
    current_user.totp_secret = secret
    current_user.totp_backup_codes = backup_codes_to_json(backup)
    current_user.totp_enabled = False
    db.commit()
    return TotpSetupResponse(
        secret=secret,
        provisioning_uri=totp_provisioning_uri(secret, current_user.email),
        backup_codes=backup,
    )


@router.post("/enable")
def totp_enable(
    body: TotpCodeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Run setup first")
    if not verify_totp(current_user.totp_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    current_user.totp_enabled = True
    bump_token_version(current_user)
    db.commit()
    return {"detail": "2FA enabled"}


@router.post("/disable")
def totp_disable(
    body: TotpDisableRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA not enabled")
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")
    ok = verify_totp(current_user.totp_secret or "", body.code)
    if not ok:
        used, remaining = consume_backup_code(current_user.totp_backup_codes, body.code)
        if not used:
            raise HTTPException(status_code=400, detail="Invalid code")
        current_user.totp_backup_codes = remaining
    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.totp_backup_codes = None
    bump_token_version(current_user)
    db.commit()
    return {"detail": "2FA disabled"}


@router.get("/status")
def totp_status(current_user: Annotated[User, Depends(get_current_user)]):
    return {"enabled": bool(current_user.totp_enabled)}
