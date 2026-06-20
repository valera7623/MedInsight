"""Subscription plans and monthly analysis usage tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Subscription

logger = logging.getLogger(__name__)

PLAN_FREEMIUM = "freemium"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"
VALID_PLANS = frozenset({PLAN_FREEMIUM, PLAN_PRO, PLAN_ENTERPRISE})


def plan_limit(plan_type: str) -> int:
    return {
        PLAN_FREEMIUM: settings.FREEMIUM_ANALYSIS_LIMIT,
        PLAN_PRO: settings.PRO_ANALYSIS_LIMIT,
        PLAN_ENTERPRISE: settings.ENTERPRISE_ANALYSIS_LIMIT,
    }.get(plan_type, settings.FREEMIUM_ANALYSIS_LIMIT)


def _period_end(start: datetime) -> datetime:
    return start + timedelta(days=30)


def get_or_create_subscription(db: Session, tenant_id: int, user_id: int | None = None) -> Subscription:
    sub = db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id).order_by(Subscription.id.desc())
    ).scalars().first()
    if sub is None:
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id,
            user_id=user_id,
            plan_type=PLAN_FREEMIUM,
            status="active",
            reports_limit=plan_limit(PLAN_FREEMIUM),
            reports_used=0,
            current_period_start=now,
            current_period_end=_period_end(now),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return _maybe_reset_period(db, sub)


def _maybe_reset_period(db: Session, sub: Subscription) -> Subscription:
    now = datetime.utcnow()
    if sub.current_period_end and now >= sub.current_period_end:
        sub.current_period_start = now
        sub.current_period_end = _period_end(now)
        sub.reports_used = 0
        db.commit()
        db.refresh(sub)
    return sub


def set_plan(
    db: Session,
    tenant_id: int,
    plan_type: str,
    *,
    status: str = "active",
    user_id: int | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    yookassa_payment_id: str | None = None,
) -> Subscription:
    sub = get_or_create_subscription(db, tenant_id, user_id)
    sub.plan_type = plan_type if plan_type in VALID_PLANS else PLAN_FREEMIUM
    sub.reports_limit = plan_limit(sub.plan_type)
    sub.status = status
    now = datetime.utcnow()
    sub.current_period_start = now
    sub.current_period_end = _period_end(now)
    sub.reports_used = 0
    if stripe_customer_id:
        sub.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id:
        sub.stripe_subscription_id = stripe_subscription_id
    if yookassa_payment_id:
        sub.yookassa_payment_id = yookassa_payment_id
    db.commit()
    db.refresh(sub)
    logger.info("Tenant %s plan set to %s (%s)", tenant_id, sub.plan_type, status)
    return sub


def check_analysis_limit(tenant_id: int) -> bool:
    """Return True if the tenant may run another analysis this period."""
    db = SessionLocal()
    try:
        sub = get_or_create_subscription(db, tenant_id)
        if sub.status not in ("active", "trialing"):
            return False
        return sub.reports_used < sub.reports_limit
    finally:
        db.close()


def increment_usage(tenant_id: int, amount: int = 1) -> int:
    """Increment usage counter. Returns new usage count."""
    db = SessionLocal()
    try:
        sub = get_or_create_subscription(db, tenant_id)
        sub.reports_used = (sub.reports_used or 0) + amount
        db.commit()
        return sub.reports_used
    finally:
        db.close()


def get_remaining(tenant_id: int) -> int:
    db = SessionLocal()
    try:
        sub = get_or_create_subscription(db, tenant_id)
        return max(0, sub.reports_limit - sub.reports_used)
    finally:
        db.close()
