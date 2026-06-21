"""Payment + subscription management endpoints (Stripe + ЮKassa)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import Payment, User
from app.services.access import effective_tenant_id
from app.services.payment import stripe_client, yookassa_client
from app.services.payment.billing_config import TESTING_UNLIMITED, billing_enabled
from app.services.payment.usage_tracker import (
    VALID_PLANS,
    get_or_create_subscription,
    get_remaining,
    set_plan,
)

router = APIRouter(prefix="/payments", tags=["payments"])


class CheckoutRequest(BaseModel):
    plan_type: str  # pro | enterprise


class SubscriptionResponse(BaseModel):
    plan_type: str
    status: str
    reports_limit: int
    reports_used: int
    reports_remaining: int
    current_period_end: datetime | None


def _require_tenant(user: User, request: Request) -> int:
    tid = effective_tenant_id(user, get_request_tenant_id(request))
    if tid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant required")
    return tid


@router.get("/prices")
def list_prices():
    return {
        "plans": [
            {
                "plan_type": "freemium",
                "name": "Freemium",
                "analysis_limit": settings.FREEMIUM_ANALYSIS_LIMIT,
                "price_rub": 0,
                "price_usd": 0,
            },
            {
                "plan_type": "pro",
                "name": "Pro",
                "analysis_limit": settings.PRO_ANALYSIS_LIMIT,
                "price_rub": settings.PRO_PRICE_RUB,
                "price_usd": settings.PRO_PRICE_USD,
            },
            {
                "plan_type": "enterprise",
                "name": "Enterprise",
                "analysis_limit": settings.ENTERPRISE_ANALYSIS_LIMIT,
                "price_rub": settings.ENTERPRISE_PRICE_RUB,
                "price_usd": settings.ENTERPRISE_PRICE_USD,
            },
        ],
        "billing_enabled": billing_enabled(),
        "providers": {
            "stripe": stripe_client.is_configured(),
            "yookassa": yookassa_client.is_configured(),
        },
    }


@router.post("/create-checkout")
def create_checkout(
    data: CheckoutRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not billing_enabled():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is disabled")
    tenant_id = _require_tenant(current_user, request)
    if data.plan_type not in {"pro", "enterprise"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan_type")
    try:
        return stripe_client.create_checkout_session(
            data.plan_type, tenant_id, current_user.id, customer_email=current_user.email
        )
    except stripe_client.StripeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/yookassa/create")
def create_yookassa(
    data: CheckoutRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not billing_enabled():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is disabled")
    tenant_id = _require_tenant(current_user, request)
    if data.plan_type not in {"pro", "enterprise"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan_type")
    try:
        return yookassa_client.create_payment(data.plan_type, tenant_id, current_user.id)
    except yookassa_client.YooKassaError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not billing_enabled():
        # Testing / maintenance mode: report unlimited usage, no real subscription.
        return SubscriptionResponse(
            plan_type="freemium",
            status="testing",
            reports_limit=TESTING_UNLIMITED,
            reports_used=0,
            reports_remaining=TESTING_UNLIMITED,
            current_period_end=None,
        )
    tenant_id = _require_tenant(current_user, request)
    sub = get_or_create_subscription(db, tenant_id, current_user.id)
    return SubscriptionResponse(
        plan_type=sub.plan_type,
        status=sub.status,
        reports_limit=sub.reports_limit,
        reports_used=sub.reports_used,
        reports_remaining=max(0, sub.reports_limit - sub.reports_used),
        current_period_end=sub.current_period_end,
    )


@router.post("/cancel-subscription")
def cancel_subscription(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = _require_tenant(current_user, request)
    sub = get_or_create_subscription(db, tenant_id, current_user.id)
    if sub.stripe_subscription_id:
        try:
            stripe_client.cancel_subscription(sub.stripe_subscription_id)
        except stripe_client.StripeError:
            pass
    set_plan(db, tenant_id, "freemium", status="canceled", user_id=current_user.id)
    return {"status": "canceled", "plan_type": "freemium", "reports_remaining": get_remaining(tenant_id)}


@router.get("/history")
def payment_history(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    from sqlalchemy import select

    tenant_id = _require_tenant(current_user, request)
    rows = (
        db.execute(
            select(Payment).where(Payment.tenant_id == tenant_id).order_by(Payment.created_at.desc()).limit(50)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": p.id,
            "provider": p.provider,
            "amount": p.amount,
            "currency": p.currency,
            "status": p.status,
            "description": p.description,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]
