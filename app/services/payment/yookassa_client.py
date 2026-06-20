"""ЮKassa payment helpers (graceful when SDK/keys absent)."""

from __future__ import annotations

import logging
import uuid

from app.config import settings

logger = logging.getLogger(__name__)


class YooKassaError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY)


def _configure():
    try:
        from yookassa import Configuration
    except ImportError as exc:
        raise YooKassaError("yookassa SDK not installed") from exc
    if not is_configured():
        raise YooKassaError("YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY not configured")
    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


def plan_amount_rub(plan_type: str) -> int:
    """Return plan price in kopecks."""
    return {
        "pro": settings.PRO_PRICE_RUB,
        "enterprise": settings.ENTERPRISE_PRICE_RUB,
    }.get(plan_type, 0)


def create_payment(plan_type: str, tenant_id: int, user_id: int) -> dict:
    """Create a ЮKassa payment and return confirmation URL + payment id."""
    _configure()
    from yookassa import Payment

    amount_kopecks = plan_amount_rub(plan_type)
    if amount_kopecks <= 0:
        raise YooKassaError(f"No ЮKassa price configured for plan '{plan_type}'")

    amount_rub = f"{amount_kopecks / 100:.2f}"
    idempotence_key = str(uuid.uuid4())
    payment = Payment.create(
        {
            "amount": {"value": amount_rub, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": settings.YOOKASSA_RETURN_URL_SUCCESS},
            "capture": True,
            "description": f"MedInsight {plan_type} (tenant {tenant_id})",
            "metadata": {"tenant_id": str(tenant_id), "user_id": str(user_id), "plan_type": plan_type},
        },
        idempotence_key,
    )
    return {
        "payment_id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
        "status": payment.status,
        "amount": amount_kopecks,
    }


def get_payment(payment_id: str):
    _configure()
    from yookassa import Payment

    return Payment.find_one(payment_id)
