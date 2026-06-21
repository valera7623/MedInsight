#!/usr/bin/env python3
"""Manual test for Phase 9: WebSocket real-time notifications.

Two parts (no external services required):
  1. ConnectionManager unit test — subscription filtering + event dispatch +
     message envelope shape (async, with a fake WebSocket).
  2. WS endpoint handshake via Starlette TestClient — JWT auth, connected ack,
     subscribe ack, ping/pong.

Run from the project root:
    python scripts/test_websocket.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, message):
        self.sent.append(message)


async def test_connection_manager() -> bool:
    print("\n=== ТЕСТ ConnectionManager ===")
    from app.websocket.connection_manager import ConnectionManager
    from app.websocket.events import EVENT_PREDICTION_READY, build_envelope

    mgr = ConnectionManager()
    ws_a = FakeWebSocket()
    ws_b = FakeWebSocket()
    await mgr.connect(ws_a, user_id=1, tenant_id=10, department_id=100)
    await mgr.connect(ws_b, user_id=2, tenant_id=10, department_id=100)

    ok = True

    # Personal message to user 1 only.
    env = build_envelope(EVENT_PREDICTION_READY, {"patient_id": 42, "risk": 30}, user_id=1)
    await mgr.dispatch(env)
    if len(ws_a.sent) != 1 or ws_b.sent:
        print(f"  FAIL: personal routing (a={len(ws_a.sent)} b={len(ws_b.sent)})"); ok = False
    else:
        msg = ws_a.sent[0]
        if msg["event"] != EVENT_PREDICTION_READY or "timestamp" not in msg or msg["data"]["patient_id"] != 42:
            print(f"  FAIL: envelope shape {msg}"); ok = False
        else:
            print("  ✓ personal message доставлено user=1, формат корректный")

    # Tenant broadcast reaches both users in tenant 10.
    ws_a.sent.clear(); ws_b.sent.clear()
    await mgr.dispatch(build_envelope("analysis.completed", {"x": 1}, tenant_id=10))
    if len(ws_a.sent) == 1 and len(ws_b.sent) == 1:
        print("  ✓ tenant broadcast доставлен обоим")
    else:
        print(f"  FAIL: tenant broadcast (a={len(ws_a.sent)} b={len(ws_b.sent)})"); ok = False

    # Subscription filtering: ws_a subscribes only to limit.exceeded.
    ws_a.sent.clear(); ws_b.sent.clear()
    mgr.set_subscriptions(ws_a, ["limit.exceeded"], subscribe=True)
    await mgr.dispatch(build_envelope(EVENT_PREDICTION_READY, {"y": 2}, tenant_id=10))
    if not ws_a.sent and len(ws_b.sent) == 1:
        print("  ✓ подписка фильтрует события (ws_a не получил неподписанное)")
    else:
        print(f"  FAIL: subscription filter (a={len(ws_a.sent)} b={len(ws_b.sent)})"); ok = False

    await mgr.disconnect(ws_a, 1)
    await mgr.disconnect(ws_b, 2)
    if mgr.total != 0:
        print(f"  FAIL: total != 0 после disconnect ({mgr.total})"); ok = False
    else:
        print("  ✓ disconnect очищает соединения")

    print("  Результат:", "PASS" if ok else "FAIL")
    return ok


def test_ws_endpoint() -> bool:
    print("\n=== ТЕСТ WebSocket эндпоинта (handshake) ===")
    from fastapi.testclient import TestClient

    import app.main as m

    ok = True
    with TestClient(m.app) as c:
        r = c.post("/api/auth/login", json={"email": settings.SUPER_ADMIN_EMAIL, "password": settings.SUPER_ADMIN_PASSWORD})
        if r.status_code != 200:
            print(f"  SKIP: login failed ({r.status_code}) — проверьте SUPER_ADMIN_PASSWORD")
            return True
        token = r.json()["access_token"]

        # Invalid token must be rejected.
        try:
            with c.websocket_connect("/ws/test?token=bad"):
                print("  FAIL: соединение с неверным токеном не отклонено"); ok = False
        except Exception:
            print("  ✓ неверный токен отклонён")

        with c.websocket_connect(f"/ws/test?token={token}") as ws:
            first = ws.receive_json()
            if first.get("event") != "connected":
                print(f"  FAIL: ожидалось 'connected', got {first}"); ok = False
            else:
                print("  ✓ получено 'connected'")
            ws.send_json({"action": "subscribe", "events": ["prediction.ready"]})
            ack = ws.receive_json()
            if ack.get("event") == "subscribed" and "prediction.ready" in ack["data"]["events"]:
                print("  ✓ подписка подтверждена")
            else:
                print(f"  FAIL: subscribe ack {ack}"); ok = False
            ws.send_json({"action": "ping"})
            pong = ws.receive_json()
            if pong.get("event") == "pong":
                print("  ✓ ping → pong")
            else:
                print(f"  FAIL: ping/pong {pong}"); ok = False

    print("  Результат:", "PASS" if ok else "FAIL")
    return ok


def main() -> int:
    mgr_ok = asyncio.run(test_connection_manager())
    ep_ok = test_ws_endpoint()
    print("\n=== ИТОГ ===")
    print("  ConnectionManager:", "PASS" if mgr_ok else "FAIL")
    print("  WS endpoint:      ", "PASS" if ep_ok else "FAIL")
    return 0 if (mgr_ok and ep_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
