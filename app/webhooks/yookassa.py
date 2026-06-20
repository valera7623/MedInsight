"""Inbound ЮKassa webhook (no auth — payment id re-verified via API when possible)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Payment
from app.services.payment import yookassa_client
from app.services.payment.usage_tracker import set_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["payment-webhooks"])


@router.post("/yookassa")
async def yookassa_webhook(request: Request, db: Annotated[Session, Depends(get_db)]):
    try:
        body = await request.json()
    except Exception:
        return {"received": False}

    event = body.get("event", "")
    obj = body.get("object", {}) or {}
    metadata = obj.get("metadata", {}) or {}
    payment_id = obj.get("id", "")
    logger.info("ЮKassa webhook: %s (payment=%s)", event, payment_id)

    # Best-effort re-verification against the ЮKassa API.
    verified_status = obj.get("status")
    if payment_id and yookassa_client.is_configured():
        try:
            remote = yookassa_client.get_payment(payment_id)
            verified_status = getattr(remote, "status", verified_status)
            meta = getattr(remote, "metadata", None)
            if meta:
                metadata = dict(meta)
        except Exception as exc:
            logger.warning("ЮKassa re-verification failed for %s: %s", payment_id, exc)

    tenant_id = _to_int(metadata.get("tenant_id"))
    user_id = _to_int(metadata.get("user_id"))
    plan_type = metadata.get("plan_type", "pro")
    amount = _amount_to_kopecks(obj.get("amount", {}))

    if event == "payment.succeeded" and verified_status == "succeeded" and tenant_id:
        set_plan(db, tenant_id, plan_type, status="active", user_id=user_id, yookassa_payment_id=payment_id)
        _record_payment(db, tenant_id, user_id, payment_id, amount, "succeeded", f"ЮKassa {plan_type}")
    elif event in ("payment.canceled", "payment.waiting_for_capture") and tenant_id:
        if event == "payment.canceled":
            _record_payment(db, tenant_id, user_id, payment_id, amount, "failed", f"ЮKassa {plan_type} canceled")

    return {"received": True}


def _to_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _amount_to_kopecks(amount: dict) -> int:
    try:
        return int(round(float(amount.get("value", 0)) * 100))
    except (ValueError, TypeError):
        return 0


def _record_payment(db, tenant_id, user_id, pid, amount, pstatus, description) -> None:
    db.add(
        Payment(
            tenant_id=tenant_id, user_id=user_id, provider="yookassa",
            provider_payment_id=pid, amount=amount, currency="RUB",
            status=pstatus, description=description,
        )
    )
    db.commit()
