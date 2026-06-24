"""WebSocket event publishing + Redis pub/sub fan-in.

``publish_event`` is callable from anywhere (API handler, Celery worker). It
publishes a JSON envelope onto a Redis channel; the FastAPI process runs
``run_event_listener`` which receives envelopes and dispatches them to the local
WebSocket connections. This bridges the API and worker processes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

WS_CHANNEL = "medinsight:ws_events"

# Event names
EVENT_PREDICTION_READY = "prediction.ready"
EVENT_ANALYSIS_COMPLETED = "analysis.completed"
EVENT_LIMIT_EXCEEDED = "limit.exceeded"
EVENT_DOCUMENT_PARSED = "document.parsed"
EVENT_PATIENT_UPDATED = "patient.updated"
EVENT_DICOM_READY = "dicom.ready"
EVENT_APPOINTMENT_REMINDER = "appointment.reminder"
EVENT_APPOINTMENT_CREATED = "appointment.created"
EVENT_APPOINTMENT_UPDATED = "appointment.updated"

KNOWN_EVENTS = {
    EVENT_PREDICTION_READY, EVENT_ANALYSIS_COMPLETED, EVENT_LIMIT_EXCEEDED,
    EVENT_DOCUMENT_PARSED, EVENT_PATIENT_UPDATED, EVENT_DICOM_READY,
    EVENT_APPOINTMENT_REMINDER, EVENT_APPOINTMENT_CREATED, EVENT_APPOINTMENT_UPDATED,
}


def build_envelope(
    event: str, data: dict[str, Any], *,
    user_id: int | None = None, tenant_id: int | None = None, department_id: int | None = None,
) -> dict[str, Any]:
    return {
        "event": event,
        "data": data,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "department_id": department_id,
    }


def publish_event(
    event: str, data: dict[str, Any], *,
    user_id: int | None = None, tenant_id: int | None = None, department_id: int | None = None,
) -> None:
    """Publish an event for real-time delivery. Best-effort, never raises."""
    if not settings.WEBSOCKET_ENABLED:
        return
    envelope = build_envelope(event, data, user_id=user_id, tenant_id=tenant_id, department_id=department_id)
    client = get_redis()
    if client is None:
        logger.debug("WS publish skipped (no Redis): %s", event)
        return
    try:
        client.publish(WS_CHANNEL, json.dumps(envelope))
    except Exception as exc:  # noqa: BLE001
        logger.warning("WS publish failed for %s: %s", event, exc)


async def run_event_listener(manager) -> None:
    """Background task: subscribe to Redis and dispatch to local sockets."""
    if not settings.WEBSOCKET_ENABLED:
        return
    try:
        import redis.asyncio as aioredis
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis.asyncio unavailable (%s) — WS fan-in disabled", exc)
        return

    from app.core.metrics import websocket_messages_received_total

    while True:
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(WS_CHANNEL)
            logger.info("WS event listener subscribed to %s", WS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                    websocket_messages_received_total.inc()
                    await manager.dispatch(envelope)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("WS dispatch error: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("WS listener error (%s) — reconnecting in 5s", exc)
            import asyncio
            await asyncio.sleep(5)
