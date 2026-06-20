"""Outbound webhook delivery with HMAC-SHA256 signatures and retry/backoff."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Webhook

logger = logging.getLogger(__name__)

VALID_EVENTS = frozenset({"analysis.completed", "prediction.ready", "patient.updated"})
USER_AGENT = "MedInsight-Webhook/1.0"


def sign_payload(secret: str, body: str) -> str:
    """Return hex HMAC-SHA256 signature over the exact transmitted body."""
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: str, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, body), signature)


def build_payload(event: str, tenant_id: int, **fields: Any) -> dict[str, Any]:
    payload = {
        "event": event,
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    payload.update({k: v for k, v in fields.items() if v is not None})
    return payload


def deliver_one(url: str, payload: dict[str, Any], secret: str | None) -> bool:
    """POST one webhook with retries + exponential backoff. Returns success."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if secret:
        headers["X-Webhook-Signature"] = sign_payload(secret, body)

    max_attempts = settings.WEBHOOK_RETRY_COUNT + 1
    delay = settings.WEBHOOK_RETRY_DELAY_SECONDS

    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_SECONDS, follow_redirects=False) as client:
                resp = client.post(url, content=body, headers=headers)
            if 200 <= resp.status_code < 300:
                logger.info("Webhook delivered to %s (event=%s, attempt=%d)", url[:120], payload.get("event"), attempt)
                return True
            logger.warning("Webhook non-2xx %s status=%d attempt=%d", url[:120], resp.status_code, attempt)
        except Exception as exc:
            logger.warning("Webhook error %s attempt=%d: %s", url[:120], attempt, exc)
        if attempt < max_attempts:
            time.sleep(delay * (2 ** (attempt - 1)))
    return False


def _record_result(webhook_id: int, success: bool) -> None:
    db = SessionLocal()
    try:
        wh = db.get(Webhook, webhook_id)
        if not wh:
            return
        if success:
            wh.last_triggered_at = datetime.utcnow()
            wh.failure_count = 0
        else:
            wh.failure_count = (wh.failure_count or 0) + 1
            if wh.failure_count > settings.WEBHOOK_FAILURE_DEACTIVATE_THRESHOLD:
                wh.is_active = False
                logger.error("Webhook %s auto-deactivated after %d failures", webhook_id, wh.failure_count)
        db.commit()
    finally:
        db.close()


def dispatch_event(event: str, tenant_id: int, payload: dict[str, Any]) -> int:
    """Deliver an event to all active webhooks of a tenant subscribed to it.

    Returns the number of webhooks that received the event successfully. Runs
    synchronously; call from a Celery task or background thread.
    """
    if not settings.WEBHOOK_ENABLED or event not in VALID_EVENTS:
        return 0

    db = SessionLocal()
    try:
        webhooks = (
            db.execute(
                select(Webhook).where(Webhook.tenant_id == tenant_id, Webhook.is_active.is_(True))
            )
            .scalars()
            .all()
        )
        targets = [
            (wh.id, wh.url, wh.secret)
            for wh in webhooks
            if not wh.events or event in (wh.events or [])
        ]
    finally:
        db.close()

    delivered = 0
    for webhook_id, url, secret in targets:
        success = deliver_one(url, payload, secret)
        _record_result(webhook_id, success)
        if success:
            delivered += 1
    return delivered
