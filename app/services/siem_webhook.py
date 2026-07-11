"""Real-time SIEM webhook dispatch alongside batch export."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def push_audit_event(payload: dict) -> None:
    if not settings.SIEM_WEBHOOK_ENABLED or not settings.SIEM_WEBHOOK_URL:
        return
    try:
        httpx.post(settings.SIEM_WEBHOOK_URL, json=payload, timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("SIEM webhook push failed: %s", exc)
