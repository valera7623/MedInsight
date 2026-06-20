"""Webhook management endpoints."""

from __future__ import annotations

import secrets as secrets_lib
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import User, Webhook
from app.services.access import effective_tenant_id
from app.services.webhook_sender import VALID_EVENTS, build_payload, deliver_one

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: list(VALID_EVENTS))
    secret: str | None = None


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = None
    is_active: bool | None = None
    secret: str | None = None


class WebhookResponse(BaseModel):
    id: int
    tenant_id: int
    url: str
    events: list[str] | None
    is_active: bool
    created_at: datetime
    last_triggered_at: datetime | None
    failure_count: int
    has_secret: bool = False

    model_config = {"from_attributes": True}


def _validate_events(events: list[str]) -> list[str]:
    invalid = [e for e in events if e not in VALID_EVENTS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid events: {', '.join(invalid)}. Allowed: {', '.join(sorted(VALID_EVENTS))}",
        )
    return events


def _require_tenant(user: User, request: Request) -> int:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    if tid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant required")
    return tid


def _serialize(wh: Webhook) -> WebhookResponse:
    return WebhookResponse(
        id=wh.id,
        tenant_id=wh.tenant_id,
        url=wh.url,
        events=wh.events,
        is_active=wh.is_active,
        created_at=wh.created_at,
        last_triggered_at=wh.last_triggered_at,
        failure_count=wh.failure_count,
        has_secret=bool(wh.secret),
    )


@router.post("/register", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def register_webhook(
    data: WebhookCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = _require_tenant(current_user, request)
    events = _validate_events(data.events or list(VALID_EVENTS))
    wh = Webhook(
        tenant_id=tenant_id,
        url=str(data.url),
        secret=(data.secret or secrets_lib.token_hex(16)),
        events=events,
        is_active=True,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return _serialize(wh)


@router.get("", response_model=list[WebhookResponse])
def list_webhooks(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = _require_tenant(current_user, request)
    rows = (
        db.execute(select(Webhook).where(Webhook.tenant_id == tenant_id).order_by(Webhook.created_at.desc()))
        .scalars()
        .all()
    )
    return [_serialize(w) for w in rows]


def _get_owned(db: Session, webhook_id: int, tenant_id: int) -> Webhook:
    wh = db.get(Webhook, webhook_id)
    if not wh or wh.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return wh


@router.put("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    webhook_id: int,
    data: WebhookUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = _require_tenant(current_user, request)
    wh = _get_owned(db, webhook_id, tenant_id)
    if data.url is not None:
        wh.url = str(data.url)
    if data.events is not None:
        wh.events = _validate_events(data.events)
    if data.is_active is not None:
        wh.is_active = data.is_active
        if data.is_active:
            wh.failure_count = 0
    if data.secret is not None:
        wh.secret = data.secret or None
    db.commit()
    db.refresh(wh)
    return _serialize(wh)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = _require_tenant(current_user, request)
    wh = _get_owned(db, webhook_id, tenant_id)
    db.delete(wh)
    db.commit()


@router.post("/{webhook_id}/test")
def test_webhook(
    webhook_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = _require_tenant(current_user, request)
    wh = _get_owned(db, webhook_id, tenant_id)
    payload = build_payload(
        "analysis.completed",
        tenant_id,
        patient_id=0,
        analysis_id=0,
        result={"test": True, "message": "MedInsight webhook test"},
    )
    success = deliver_one(wh.url, payload, wh.secret)
    if success:
        wh.last_triggered_at = datetime.utcnow()
        wh.failure_count = 0
    else:
        wh.failure_count = (wh.failure_count or 0) + 1
    db.commit()
    return {"delivered": success, "url": wh.url}
