"""Stripe Checkout + subscription helpers (graceful when SDK/keys absent)."""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


class StripeError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def _client():
    try:
        import stripe
    except ImportError as exc:
        raise StripeError("stripe SDK not installed") from exc
    if not settings.STRIPE_SECRET_KEY:
        raise StripeError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def price_id_for_plan(plan_type: str) -> str | None:
    return {
        "pro": settings.STRIPE_PRICE_ID_PRO,
        "enterprise": settings.STRIPE_PRICE_ID_ENTERPRISE,
    }.get(plan_type) or None


def create_checkout_session(plan_type: str, tenant_id: int, user_id: int, customer_email: str | None = None) -> dict:
    """Create a Stripe Checkout Session for a subscription plan."""
    stripe = _client()
    price_id = price_id_for_plan(plan_type)
    if not price_id:
        raise StripeError(f"No Stripe price configured for plan '{plan_type}'")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=settings.STRIPE_SUCCESS_URL,
        cancel_url=settings.STRIPE_CANCEL_URL,
        customer_email=customer_email,
        client_reference_id=str(tenant_id),
        metadata={"tenant_id": str(tenant_id), "user_id": str(user_id), "plan_type": plan_type},
        subscription_data={"metadata": {"tenant_id": str(tenant_id), "plan_type": plan_type}},
    )
    return {"checkout_url": session.url, "session_id": session.id}


def cancel_subscription(stripe_subscription_id: str) -> bool:
    stripe = _client()
    stripe.Subscription.delete(stripe_subscription_id)
    return True


def verify_webhook(payload: bytes, signature: str) -> dict:
    """Verify a Stripe webhook signature and return the parsed event."""
    stripe = _client()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise StripeError("STRIPE_WEBHOOK_SECRET not configured")
    return stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
