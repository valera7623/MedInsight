"""Phase 4 smoke tests: self-healing RAG, webhooks, payments.

Run standalone with an isolated temp DB:

    python scripts/test_phase4.py

Exercises:
  1. Self-healing — a flaky function is auto-retried using a KB fix.
  2. Webhooks   — register a webhook, fire an event, verify HMAC delivery.
  3. Payments   — plan limits, usage tracking, and the 402 limit guard.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolated environment BEFORE importing the app.
_TMP_DB = os.path.join(tempfile.gettempdir(), "medinsight_phase4_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DB}")
os.environ.setdefault("ENCRYPTION_ENABLED", "false")
os.environ.setdefault("TENANT_MODE", "true")
os.environ.setdefault("SELF_HEALING_ENABLED", "true")
os.environ.setdefault("WEBHOOK_ENABLED", "true")
os.environ.setdefault("WEBHOOK_RETRY_COUNT", "0")
os.environ.setdefault("CHROMA_PERSIST_DIR", os.path.join(tempfile.gettempdir(), "medinsight_phase4_chroma"))

PASSED = 0
FAILED = 0


def check(label: str, ok: bool, extra: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"PASS  {label} {extra}")
    else:
        FAILED += 1
        print(f"FAIL  {label} {extra}")


# --------------------------------------------------------------------------
# 1. Self-healing
# --------------------------------------------------------------------------


def test_self_healing() -> None:
    print("\n=== 1. Self-healing RAG ===")
    from app.database import Base, engine
    from app.services.self_healing import with_self_healing
    from app.services.self_healing.vector_store import get_knowledge_base, reset_knowledge_base

    Base.metadata.create_all(bind=engine)
    reset_knowledge_base()
    kb = get_knowledge_base()
    check("knowledge base available", kb is not None)
    if kb is None:
        return

    kb.add_error(
        {
            "error_text": "transient parser failure tokenizing data valueerror flaky",
            "error_type": "ValueError",
            "agent_name": "tester",
            "solution_prompt": "retry the operation",
            "solution_code": {"action": "retry_simple", "params": {}},
            "was_successful": True,
            "success_count": 3,
            "fail_count": 0,
        }
    )

    state = {"calls": 0}

    @with_self_healing("tester")
    def flaky(*, patient_id=None, tenant_id=None):
        state["calls"] += 1
        if state["calls"] == 1:
            raise ValueError("transient parser failure tokenizing data flaky")
        return {"ok": True}

    result = flaky(patient_id=1)
    check("flaky function auto-healed", result == {"ok": True}, f"(calls={state['calls']})")
    check("fix retried exactly once", state["calls"] == 2)

    stats = kb.get_stats()
    check("KB stats report fixes", stats["total_fixes"] >= 1, f"(total={stats['total_fixes']})")


# --------------------------------------------------------------------------
# 2. Webhooks
# --------------------------------------------------------------------------


class _Receiver(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        _Receiver.received.append(
            {"body": body, "signature": self.headers.get("X-Webhook-Signature", "")}
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence
        pass


def test_webhooks() -> None:
    print("\n=== 2. Webhooks ===")
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app
    from app.services.webhook_sender import dispatch_event, sign_payload, verify_signature

    _Receiver.received.clear()
    server = HTTPServer(("127.0.0.1", 0), _Receiver)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    target_url = f"http://127.0.0.1:{port}/hook"

    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/login",
            json={"email": settings.SUPER_ADMIN_EMAIL, "password": settings.SUPER_ADMIN_PASSWORD},
        ).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        tid = c.post("/api/admin/tenants", headers=H, json={"name": "WH", "subdomain": "whtest"}).json()["id"]
        TH = {**H, "X-Tenant-ID": str(tid)}

        reg = c.post("/api/webhooks/register", headers=TH, json={"url": target_url, "secret": "topsecret"})
        check("register webhook", reg.status_code == 201, f"({reg.status_code})")
        wid = reg.json().get("id")

        listed = c.get("/api/webhooks", headers=TH)
        check("list webhooks", listed.status_code == 200 and len(listed.json()) == 1)

        test_resp = c.post(f"/api/webhooks/{wid}/test", headers=TH)
        check("test webhook delivered", test_resp.status_code == 200 and test_resp.json().get("delivered") is True)

        # Fire a real event through the dispatcher.
        delivered = dispatch_event(
            "prediction.ready",
            tid,
            {"event": "prediction.ready", "tenant_id": tid, "patient_id": 1, "result": {"risk": 42}},
        )
        check("dispatch_event delivered", delivered == 1, f"(delivered={delivered})")

    server.shutdown()

    check("receiver got requests", len(_Receiver.received) >= 2, f"(count={len(_Receiver.received)})")
    if _Receiver.received:
        last = _Receiver.received[-1]
        valid = verify_signature("topsecret", last["body"], last["signature"])
        check("HMAC-SHA256 signature valid", valid)
        # Negative check: wrong secret must fail.
        check("HMAC rejects wrong secret", not verify_signature("wrong", last["body"], last["signature"]))


# --------------------------------------------------------------------------
# 3. Payments
# --------------------------------------------------------------------------


def test_payments() -> None:
    print("\n=== 3. Payments + usage limits ===")
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app
    from app.services.payment.usage_tracker import check_analysis_limit, get_remaining, increment_usage

    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/login",
            json={"email": settings.SUPER_ADMIN_EMAIL, "password": settings.SUPER_ADMIN_PASSWORD},
        ).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        tid = c.post("/api/admin/tenants", headers=H, json={"name": "Pay", "subdomain": "paytest"}).json()["id"]
        c.post(
            "/api/admin/users",
            headers=H,
            json={"email": "doc@paytest.com", "password": "secret1", "full_name": "D", "role": "doctor", "tenant_id": tid},
        )
        dtok = c.post(
            "/api/auth/login", json={"email": "doc@paytest.com", "password": "secret1", "subdomain": "paytest"}
        ).json()["access_token"]
        DH = {"Authorization": f"Bearer {dtok}", "X-Tenant-ID": str(tid)}

        prices = c.get("/api/payments/prices", headers=DH)
        check("prices endpoint", prices.status_code == 200 and len(prices.json()["plans"]) == 3)

        sub = c.get("/api/payments/subscription", headers=DH).json()
        check("default plan freemium", sub["plan_type"] == "freemium", f"({sub['plan_type']})")
        check("freemium limit = 5", sub["reports_limit"] == settings.FREEMIUM_ANALYSIS_LIMIT)

        # Exhaust the freemium quota directly, then verify the 402 guard.
        for _ in range(settings.FREEMIUM_ANALYSIS_LIMIT):
            increment_usage(tid)
        check("limit reached", not check_analysis_limit(tid), f"(remaining={get_remaining(tid)})")

        pid = c.post(
            "/api/patients",
            headers=DH,
            json={"first_name": "Л", "last_name": "Т", "birth_date": "1960-01-01", "gender": "M", "phone": "1"},
        ).json()["id"]
        blocked = c.post(f"/api/analytics/predict/{pid}", headers=DH)
        check("usage-limit middleware returns 402", blocked.status_code == 402, f"({blocked.status_code})")

        # Upgrade to pro lifts the limit.
        from app.database import SessionLocal
        from app.services.payment.usage_tracker import set_plan

        db = SessionLocal()
        try:
            set_plan(db, tid, "pro")
        finally:
            db.close()
        check("pro plan lifts limit", check_analysis_limit(tid), f"(remaining={get_remaining(tid)})")


def main() -> int:
    test_self_healing()
    test_webhooks()
    test_payments()
    print(f"\n{'=' * 40}\nPhase 4: {PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
