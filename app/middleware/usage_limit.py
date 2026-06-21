"""Enforce per-tenant monthly analysis limits before running predictions."""

from __future__ import annotations

import asyncio
import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.middleware.tenant import get_request_tenant_id
from app.services.payment.usage_tracker import check_analysis_limit, get_remaining

logger = logging.getLogger(__name__)

# Paths that consume an analysis credit (POST only).
LIMITED_PATHS = re.compile(r"^/api/analytics/predict/\d+$")

# Don't notify the same tenant more than once per this many seconds.
_LIMIT_NOTIFY_THROTTLE_SECONDS = 24 * 3600


class UsageLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and LIMITED_PATHS.match(request.url.path):
            tenant_id = get_request_tenant_id(request)
            if tenant_id is not None and not check_analysis_limit(tenant_id):
                logger.info("Tenant %s exceeded analysis limit", tenant_id)
                if settings.EMAIL_LIMIT_EXCEEDED_ENABLED or settings.TELEGRAM_BOT_ENABLED:
                    asyncio.create_task(_notify_limit_exceeded(tenant_id))
                try:
                    from app.services.payment.usage_tracker import get_remaining
                    from app.websocket.events import EVENT_LIMIT_EXCEEDED, publish_event

                    publish_event(
                        EVENT_LIMIT_EXCEEDED,
                        {"tenant_id": tenant_id, "remaining": get_remaining(tenant_id)},
                        tenant_id=tenant_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("WS limit.exceeded event failed: %s", exc)
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": "Месячный лимит анализов исчерпан. Обновите тарифный план.",
                        "remaining": get_remaining(tenant_id),
                        "upgrade_url": "/api/payments/prices",
                    },
                )
        return await call_next(request)


def _should_send_limit_notification(tenant_id: int) -> bool:
    """Throttle limit-exceeded notifications via Redis; fail-open if Redis is down."""
    try:
        from app.core.redis import get_redis

        client = get_redis()
        if client is None:
            return True
        key = f"limit_notify:{tenant_id}"
        return bool(client.set(key, "1", nx=True, ex=_LIMIT_NOTIFY_THROTTLE_SECONDS))
    except Exception:  # noqa: BLE001
        return True


async def _notify_limit_exceeded(tenant_id: int) -> None:
    try:
        if not _should_send_limit_notification(tenant_id):
            return

        from app.database import SessionLocal
        from app.models import User
        from app.services.email import get_email_service
        from app.services.payment.usage_tracker import get_or_create_subscription

        db = SessionLocal()
        try:
            sub = get_or_create_subscription(db, tenant_id)
            plan_type, limit = sub.plan_type, sub.reports_limit
            admin = (
                db.query(User)
                .filter(User.tenant_id == tenant_id, User.role == "admin")
                .order_by(User.id)
                .first()
            )
            if admin is None:
                admin = (
                    db.query(User)
                    .filter(User.tenant_id == tenant_id)
                    .order_by(User.id)
                    .first()
                )
            email = admin.email if admin else None
        finally:
            db.close()

        if settings.EMAIL_LIMIT_EXCEEDED_ENABLED and email:
            await get_email_service().send_limit_exceeded_email(email, plan_type, limit)
        if settings.TELEGRAM_BOT_ENABLED:
            await _notify_limit_exceeded_telegram(tenant_id, plan_type, limit)
    except Exception as exc:  # noqa: BLE001 — notifications must not affect the response
        logger.warning("Limit-exceeded notification failed for tenant %s: %s", tenant_id, exc)


async def _notify_limit_exceeded_telegram(tenant_id: int, plan_type: str, limit: int) -> None:
    if not settings.TELEGRAM_BOT_ENABLED:
        return
    try:
        from app.bot.services.notification_service import get_notification_service
        from app.services.payment.usage_tracker import get_remaining

        remaining = get_remaining(tenant_id)
        svc = get_notification_service()
        await svc.send_limit_exceeded(tenant_id, plan_type, limit, remaining)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Limit-exceeded Telegram failed for tenant %s: %s", tenant_id, exc)
