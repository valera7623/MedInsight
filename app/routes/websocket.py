"""WebSocket endpoint for real-time notifications.

Auth: ``/ws/{client_id}?token=<JWT>``. Clients may subscribe/unsubscribe to
event names and the server sends periodic heartbeats. Users only ever receive
events targeted at their own user_id / tenant / department.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from app.config import settings
from app.core.metrics import websocket_messages_received_total
from app.database import SessionLocal
from app.models import User
from app.websocket.connection_manager import manager
from app.websocket.events import KNOWN_EVENTS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


def _authenticate(token: str | None) -> tuple[int, int | None, int | None] | None:
    """Return (user_id, tenant_id, department_id) or None if invalid."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        return None
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.is_blocked:
            return None
        return user.id, user.tenant_id, user.department_id
    finally:
        db.close()


async def _heartbeat(websocket: WebSocket) -> None:
    interval = max(5, settings.WEBSOCKET_HEARTBEAT_INTERVAL)
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"event": "ping"})
    except Exception:  # noqa: BLE001 — connection closed
        return


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, token: str | None = Query(None)):
    if not settings.WEBSOCKET_ENABLED:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    identity = _authenticate(token)
    if identity is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    user_id, tenant_id, department_id = identity

    await websocket.accept()
    if manager.at_capacity():
        await websocket.send_json({"event": "error", "data": {"detail": "Server at capacity"}})
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    await manager.connect(websocket, user_id, tenant_id, department_id)
    await websocket.send_json({"event": "connected", "data": {"client_id": client_id, "user_id": user_id}})

    heartbeat = asyncio.create_task(_heartbeat(websocket))
    try:
        while True:
            msg = await websocket.receive_json()
            websocket_messages_received_total.inc()
            action = (msg or {}).get("action")
            if action in ("subscribe", "unsubscribe"):
                events = [e for e in (msg.get("events") or []) if e in KNOWN_EVENTS]
                current = manager.set_subscriptions(websocket, events, action == "subscribe")
                await websocket.send_json({"event": "subscribed", "data": {"events": sorted(current)}})
            elif action == "ping":
                await websocket.send_json({"event": "pong"})
            elif action == "pong":
                continue
            else:
                await websocket.send_json({"event": "error", "data": {"detail": "Unknown action"}})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("WS loop error: %s", exc)
    finally:
        heartbeat.cancel()
        await manager.disconnect(websocket, user_id)
