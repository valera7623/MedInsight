"""In-process registry of active WebSocket connections.

Tracks sockets per user and their tenant/department + event subscriptions, and
fans out event envelopes to the right sockets. Cross-process delivery (e.g. from
a Celery worker) is handled by the Redis pub/sub listener in ``events.py`` which
calls :meth:`ConnectionManager.dispatch`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.config import settings
from app.core.metrics import websocket_connections_total, websocket_messages_sent_total

logger = logging.getLogger(__name__)


@dataclass
class _ConnMeta:
    user_id: int
    tenant_id: int | None
    department_id: int | None
    events: set[str] = field(default_factory=set)  # empty = receive all


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = {}
        self._meta: dict[WebSocket, _ConnMeta] = {}
        self._lock = asyncio.Lock()
        self._count = 0

    @property
    def total(self) -> int:
        return self._count

    def at_capacity(self) -> bool:
        return self._count >= settings.WEBSOCKET_MAX_CONNECTIONS

    async def connect(self, websocket: WebSocket, user_id: int, tenant_id: int | None,
                      department_id: int | None) -> None:
        async with self._lock:
            self.active_connections.setdefault(user_id, []).append(websocket)
            self._meta[websocket] = _ConnMeta(user_id=user_id, tenant_id=tenant_id, department_id=department_id)
            self._count += 1
        websocket_connections_total.set(self._count)
        logger.info("WS connected: user=%s (total=%d)", user_id, self._count)

    async def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        async with self._lock:
            conns = self.active_connections.get(user_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                self.active_connections.pop(user_id, None)
            if self._meta.pop(websocket, None) is not None:
                self._count = max(0, self._count - 1)
        websocket_connections_total.set(self._count)
        logger.info("WS disconnected: user=%s (total=%d)", user_id, self._count)

    def set_subscriptions(self, websocket: WebSocket, events: list[str], subscribe: bool) -> set[str]:
        meta = self._meta.get(websocket)
        if meta is None:
            return set()
        if subscribe:
            meta.events.update(events)
        else:
            meta.events.difference_update(events)
        return set(meta.events)

    async def _safe_send(self, websocket: WebSocket, message: dict) -> bool:
        try:
            await websocket.send_json(message)
            websocket_messages_sent_total.inc()
            return True
        except Exception as exc:  # noqa: BLE001 — drop broken sockets
            logger.debug("WS send failed: %s", exc)
            return False

    def _wants(self, websocket: WebSocket, event: str) -> bool:
        meta = self._meta.get(websocket)
        if meta is None:
            return False
        return not meta.events or event in meta.events

    async def send_personal_message(self, message: dict, user_id: int) -> None:
        event = message.get("event", "")
        for ws in list(self.active_connections.get(user_id, [])):
            if self._wants(ws, event):
                await self._safe_send(ws, message)

    async def broadcast_to_tenant(self, message: dict, tenant_id: int) -> None:
        event = message.get("event", "")
        for ws, meta in list(self._meta.items()):
            if meta.tenant_id == tenant_id and self._wants(ws, event):
                await self._safe_send(ws, message)

    async def broadcast_to_department(self, message: dict, department_id: int) -> None:
        event = message.get("event", "")
        for ws, meta in list(self._meta.items()):
            if meta.department_id == department_id and self._wants(ws, event):
                await self._safe_send(ws, message)

    async def dispatch(self, envelope: dict) -> None:
        """Route an event envelope to the appropriate target."""
        if envelope.get("user_id") is not None:
            await self.send_personal_message(envelope, int(envelope["user_id"]))
        elif envelope.get("tenant_id") is not None:
            await self.broadcast_to_tenant(envelope, int(envelope["tenant_id"]))
        elif envelope.get("department_id") is not None:
            await self.broadcast_to_department(envelope, int(envelope["department_id"]))


manager = ConnectionManager()
