"""WebSocket connection manager and handshake tests."""

from __future__ import annotations

import pytest

from app.auth import create_access_token
from tests.conftest import commit, create_tenant, create_user


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, message):
        self.sent.append(message)


@pytest.mark.asyncio
async def test_connection_manager_routing():
    from app.websocket.connection_manager import ConnectionManager
    from app.websocket.events import EVENT_PREDICTION_READY, build_envelope

    mgr = ConnectionManager()
    ws_a = FakeWebSocket()
    ws_b = FakeWebSocket()
    await mgr.connect(ws_a, user_id=1, tenant_id=10, department_id=100)
    await mgr.connect(ws_b, user_id=2, tenant_id=10, department_id=100)

    env = build_envelope(EVENT_PREDICTION_READY, {"patient_id": 42, "risk": 30}, user_id=1)
    await mgr.dispatch(env)
    assert len(ws_a.sent) == 1
    assert not ws_b.sent

    ws_a.sent.clear()
    ws_b.sent.clear()
    await mgr.dispatch(build_envelope("analysis.completed", {"x": 1}, tenant_id=10))
    assert len(ws_a.sent) == 1 and len(ws_b.sent) == 1

    ws_a.sent.clear()
    ws_b.sent.clear()
    mgr.set_subscriptions(ws_a, ["limit.exceeded"], subscribe=True)
    await mgr.dispatch(build_envelope(EVENT_PREDICTION_READY, {"y": 2}, tenant_id=10))
    assert not ws_a.sent and len(ws_b.sent) == 1

    await mgr.disconnect(ws_a, 1)
    await mgr.disconnect(ws_b, 2)
    assert mgr.total == 0


def test_ws_endpoint_handshake(client, db_session):
    tenant = create_tenant(db_session, name="WS Clinic", subdomain="ws-clinic")
    user = create_user(db_session, tenant=tenant, email="ws@example.com", role="admin")
    commit(db_session)
    token = create_access_token(user)

    try:
        with client.websocket_connect("/ws/test?token=bad"):
            pytest.fail("expected invalid token rejection")
    except Exception:
        pass

    with client.websocket_connect(f"/ws/test?token={token}") as ws:
        first = ws.receive_json()
        assert first.get("event") == "connected"
        ws.send_json({"action": "subscribe", "events": ["prediction.ready"]})
        ack = ws.receive_json()
        assert ack.get("event") == "subscribed"
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong.get("event") == "pong"
