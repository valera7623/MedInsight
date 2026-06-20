"""Asynchronous webhook delivery via Celery, with sync fallback."""

from __future__ import annotations

import logging
from typing import Any

from app.services.webhook_sender import build_payload, dispatch_event
from app.tasks.celery_app import celery_app, redis_available

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.webhook_task.deliver_webhooks", bind=True)
def deliver_webhooks(self, event: str, tenant_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    delivered = dispatch_event(event, tenant_id, payload)
    return {"event": event, "tenant_id": tenant_id, "delivered": delivered}


def fire_event(event: str, tenant_id: int, **fields: Any) -> None:
    """Build payload and dispatch via Celery if Redis is up, else synchronously."""
    payload = build_payload(event, tenant_id, **fields)
    if redis_available():
        try:
            deliver_webhooks.delay(event, tenant_id, payload)
            return
        except Exception as exc:
            logger.warning("Celery webhook enqueue failed (%s) — sending sync", exc)
    try:
        dispatch_event(event, tenant_id, payload)
    except Exception as exc:
        logger.warning("Sync webhook dispatch failed for %s: %s", event, exc)
