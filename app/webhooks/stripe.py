"""Inbound Stripe webhook (no auth — verified via signature)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Payment
from app.services.payment import stripe_client
from app.services.payment.usage_tracker import set_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["payment-webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
):
    payload = await request.body()
    try:
        event = stripe_client.verify_webhook(payload, stripe_signature or "")
    except stripe_client.StripeError as exc:
        logger.warning("Stripe webhook verification failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature") from exc

    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    logger.info("Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata", {}) or {}
        tenant_id = _to_int(metadata.get("tenant_id") or obj.get("client_reference_id"))
        plan_type = metadata.get("plan_type", "pro")
        if tenant_id:
            set_plan(
                db, tenant_id, plan_type, status="active",
                user_id=_to_int(metadata.get("user_id")),
                stripe_customer_id=obj.get("customer"),
                stripe_subscription_id=obj.get("subscription"),
            )
            _record_payment(
                db, tenant_id, _to_int(metadata.get("user_id")), "stripe",
                obj.get("id", ""), int(obj.get("amount_total") or 0),
                (obj.get("currency") or "usd").upper(), "succeeded", f"Stripe {plan_type}",
            )
    elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        metadata = obj.get("metadata", {}) or {}
        tenant_id = _to_int(metadata.get("tenant_id"))
        if tenant_id:
            set_plan(db, tenant_id, "freemium", status="canceled")
    elif event_type == "customer.subscription.updated":
        metadata = obj.get("metadata", {}) or {}
        tenant_id = _to_int(metadata.get("tenant_id"))
        stripe_status = obj.get("status", "active")
        if tenant_id and stripe_status in ("active", "trialing", "past_due", "canceled"):
            plan_type = metadata.get("plan_type", "pro")
            set_plan(db, tenant_id, plan_type if stripe_status != "canceled" else "freemium", status=stripe_status)

    return {"received": True}


def _to_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _record_payment(db, tenant_id, user_id, provider, pid, amount, currency, pstatus, description) -> None:
    db.add(
        Payment(
            tenant_id=tenant_id, user_id=user_id, provider=provider,
            provider_payment_id=pid, amount=amount, currency=currency,
            status=pstatus, description=description,
        )
    )
    db.commit()
