#!/usr/bin/env python3
"""Test Telegram bot linking, subscriptions, and notification dispatch.

Usage:
  python scripts/test_telegram_bot.py              # offline checks (no token)
  python scripts/test_telegram_bot.py --send-test  # send test message (needs token + linked user)

Requires TELEGRAM_BOT_ENABLED=true and TELEGRAM_BOT_TOKEN in .env for live send.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Use isolated DB for link-code tests unless --live-db
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_ENABLED", "true")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "000000000:TEST_TOKEN_NOT_FOR_SEND")


def test_link_code_flow() -> None:
    from app.bot.services.link_codes import consume_link_code, generate_link_code

    # Without Redis this returns None — expected in CI without redis.
    code = generate_link_code(
        telegram_user_id=123456789,
        telegram_username="testuser",
        first_name="Test",
        last_name="User",
    )
    if code is None:
        print("SKIP link code (Redis unavailable)")
        return

    assert len(code) == 6 and code.isdigit(), code
    payload = consume_link_code(code)
    assert payload is not None, "code should be consumable once"
    assert payload["telegram_user_id"] == 123456789
    assert consume_link_code(code) is None, "code must be one-time"
    print("PASS link code flow")


def test_user_service_subscriptions() -> None:
    import uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models import Tenant, User
    from app.auth import hash_password
    from app.bot.services.user_service import TelegramUserService

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    Session = sessionmaker(bind=test_engine)
    db = Session()
    try:
        tenant = Tenant(name="T", subdomain=f"t-bot-{uuid.uuid4().hex[:8]}", settings={}, is_active=True)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        user = User(
            tenant_id=tenant.id,
            email="bot-test@example.com",
            password_hash=hash_password("secret"),
            full_name="Bot Tester",
            role="doctor",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        svc = TelegramUserService(db)
        assert svc.link_user(
            telegram_user_id=999888777,
            medinsight_user_id=user.id,
            telegram_username="linked",
            first_name="Linked",
        )
        subs = svc.get_subscriptions(999888777)
        assert "prediction.ready" in subs
        svc.toggle_subscription(999888777, "patient.created")
        subs2 = svc.get_subscriptions(999888777)
        assert "patient.created" in subs2
        assert svc.get_medinsight_user(999888777).id == user.id
        print("PASS user service subscriptions")
    finally:
        db.close()


def test_api_status_shape() -> None:
    import uuid

    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import Base, SessionLocal, engine, bootstrap_system
    from app.models import User
    from app.auth import hash_password, create_access_token

    Base.metadata.create_all(bind=engine)
    bootstrap_system()
    db = SessionLocal()
    email = f"status-{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        tenant_id=1,
        email=email,
        password_hash=hash_password("x"),
        full_name="Status User",
        role="doctor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user)
    db.close()

    client = TestClient(app)
    resp = client.get("/api/telegram/status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["linked"] is False
    assert body["subscriptions"] == []
    print("PASS API status shape")


def test_notification_templates() -> None:
    from app.bot.services.notification_service import TelegramNotificationService

    svc = TelegramNotificationService()
    assert svc is not None
    print(f"PASS notification service init (enabled={svc.enabled})")


def send_test_notification() -> None:
    from app.config import settings

    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token or "TEST_TOKEN" in token:
        print("FAIL --send-test: set real TELEGRAM_BOT_TOKEN in .env")
        sys.exit(1)

    chat_id = (settings.TELEGRAM_CHAT_ID or "").strip()
    if not chat_id:
        print("FAIL --send-test: set TELEGRAM_CHAT_ID in .env (your Telegram chat id)")
        sys.exit(1)

    import asyncio
    from aiogram import Bot

    async def _send():
        bot = Bot(token=token)
        try:
            await bot.send_message(
                int(chat_id),
                "🧪 <b>MedInsight test</b>\nТестовое уведомление от scripts/test_telegram_bot.py",
                parse_mode="HTML",
            )
        finally:
            await bot.session.close()

    asyncio.run(_send())
    print("PASS test message sent to TELEGRAM_CHAT_ID")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-test", action="store_true", help="Send live test message via Bot API")
    args = parser.parse_args()

    if args.send_test:
        send_test_notification()
        return

    test_link_code_flow()
    test_user_service_subscriptions()
    test_api_status_shape()
    test_notification_templates()
    print("\nAll Telegram bot tests passed.")


if __name__ == "__main__":
    main()
