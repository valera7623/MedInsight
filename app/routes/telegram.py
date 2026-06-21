"""API endpoints for Telegram account linking and subscription management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.bot.models import ALL_SUBSCRIPTION_EVENTS, EVENT_LABELS
from app.bot.services.link_codes import consume_link_code
from app.bot.services.user_service import TelegramUserService
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/telegram", tags=["telegram"])


class LinkRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class SubscribeRequest(BaseModel):
    events: list[str] = Field(default_factory=list)


@router.post("/link")
def link_telegram_account(
    body: LinkRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Confirm Telegram linking with the 6-digit code from the bot."""
    payload = consume_link_code(body.code)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или просроченный код. Отправьте /start боту для нового кода.",
        )

    svc = TelegramUserService(db)
    ok = svc.link_user(
        telegram_user_id=int(payload["telegram_user_id"]),
        medinsight_user_id=current_user.id,
        telegram_username=payload.get("telegram_username"),
        first_name=payload.get("first_name") or "",
        last_name=payload.get("last_name"),
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось привязать аккаунт")

    return {
        "status": "linked",
        "telegram_user_id": payload["telegram_user_id"],
        "subscriptions": svc.get_subscriptions(int(payload["telegram_user_id"])),
    }


@router.get("/status")
def telegram_status(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    svc = TelegramUserService(db)
    row = svc.get_by_user_id(current_user.id)
    if not row or not row.is_active:
        return {"linked": False, "subscriptions": []}

    subs = list(row.subscription_events or [])
    return {
        "linked": True,
        "telegram_user_id": row.telegram_user_id,
        "telegram_username": row.telegram_username,
        "is_active": row.is_active,
        "subscriptions": subs,
        "subscription_labels": [EVENT_LABELS.get(e, e) for e in subs],
    }


@router.post("/subscribe")
def update_telegram_subscriptions(
    body: SubscribeRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    svc = TelegramUserService(db)
    row = svc.get_by_user_id(current_user.id)
    if not row or not row.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram не привязан. Получите код через /start в боте.",
        )

    cleaned = [e for e in body.events if e in ALL_SUBSCRIPTION_EVENTS]
    svc.update_subscriptions(row.telegram_user_id, cleaned)
    return {
        "status": "updated",
        "subscriptions": cleaned,
        "subscription_labels": [EVENT_LABELS.get(e, e) for e in cleaned],
    }


@router.delete("/link")
def unlink_telegram_account(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    svc = TelegramUserService(db)
    if not svc.unlink_by_medinsight_user(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram не привязан")
    return {"status": "unlinked"}
