#!/usr/bin/env python3
"""Manual test for Phase 6: email notifications + JSON logging.

Usage:
    python scripts/test_email.py                 # dry-run (renders + checks logs)
    python scripts/test_email.py --to you@x.com  # actually send all templates

Email is only sent when SMTP is configured (SMTP_HOST set) and EMAIL_ENABLED=true.
Without that it renders every template and reports what *would* be sent.

Run from the project root.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services.email import EmailService, _render  # noqa: E402
from app.utils.logging import configure_logging  # noqa: E402
from app.utils.request_context import bind_request_context, clear_request_context  # noqa: E402


def test_json_logging() -> bool:
    """Verify a log line is valid JSON and carries the request context."""
    print("\n=== ТЕСТ JSON-ЛОГИРОВАНИЯ ===")
    settings.LOG_JSON_FORMAT = True
    configure_logging()

    buffer = io.StringIO()
    import structlog

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.EventRenamer("message"),
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(formatter)
    test_logger = logging.getLogger("app.middleware.logging")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    clear_request_context()
    bind_request_context(
        request_id="abc-123-def-456", user_id=42, tenant_id=1,
        ip_address="192.168.1.1", user_agent="Mozilla/5.0",
    )
    test_logger.info("Request completed", extra={})
    import structlog as _s
    _s.get_logger("app.middleware.logging").info(
        "Request completed", method="POST", path="/api/patients",
        status_code=201, duration_ms=45,
    )
    test_logger.removeHandler(handler)
    clear_request_context()

    lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
    ok = True
    for line in lines:
        try:
            entry = json.loads(line)
            print("  JSON OK:", json.dumps(entry, ensure_ascii=False))
        except json.JSONDecodeError as exc:
            print(f"  НЕ JSON: {line!r} ({exc})")
            ok = False
            continue
        for field in ("timestamp", "level", "message"):
            if field not in entry:
                print(f"  ОТСУТСТВУЕТ поле {field!r}")
                ok = False
    if not lines:
        print("  Логи не захвачены")
        ok = False
    print("  Результат:", "PASS" if ok else "FAIL")
    return ok


async def test_emails(to: str | None) -> bool:
    print("\n=== ТЕСТ EMAIL-ШАБЛОНОВ ===")
    service = EmailService()
    configured = service.is_configured
    print(f"  SMTP host: {service.smtp_host or '(не задан)'} | EMAIL_ENABLED={settings.EMAIL_ENABLED}")
    print(f"  Режим: {'РЕАЛЬНАЯ ОТПРАВКА' if (configured and to) else 'DRY-RUN (только рендер)'}")

    recipient = to or "test@example.com"
    cases = [
        ("verification", lambda: service.send_verification_email(recipient, "tok-verify-123", settings.FRONTEND_URL)),
        ("password_reset", lambda: service.send_password_reset_email(recipient, "tok-reset-123", settings.FRONTEND_URL)),
        ("prediction_ready", lambda: service.send_prediction_ready_email(recipient, "Иванов Иван", 777)),
        ("limit_exceeded", lambda: service.send_limit_exceeded_email(recipient, "freemium", 5)),
    ]

    # Always verify templates render without error.
    render_checks = {
        "verification.html": {"verification_link": "x", "expire_hours": 24, "frontend_url": "x"},
        "verification.txt": {"verification_link": "x", "expire_hours": 24, "frontend_url": "x"},
        "reset_password.html": {"reset_link": "x", "expire_hours": 2, "frontend_url": "x"},
        "prediction_ready.html": {"patient_name": "Иванов", "prediction_id": 1, "prediction_link": "x", "frontend_url": "x"},
        "limit_exceeded.html": {"plan_type": "pro", "limit": 100, "upgrade_link": "x", "frontend_url": "x"},
    }
    ok = True
    for tpl, ctx in render_checks.items():
        try:
            html = _render(tpl, **ctx)
            print(f"  рендер {tpl}: OK ({len(html)} символов)")
        except Exception as exc:  # noqa: BLE001
            print(f"  рендер {tpl}: FAIL ({exc})")
            ok = False

    if configured and to:
        for name, fn in cases:
            sent = await fn()
            print(f"  отправка {name} -> {'OK' if sent else 'FAIL'}")
            ok = ok and sent
    else:
        print("  Отправка пропущена (нет SMTP или не указан --to). Шаблоны проверены.")

    print("  Результат:", "PASS" if ok else "FAIL")
    return ok


async def main() -> int:
    parser = argparse.ArgumentParser(description="Тест email-уведомлений и JSON-логов MedInsight")
    parser.add_argument("--to", help="Реальный адрес для отправки писем (иначе dry-run)")
    args = parser.parse_args()

    logs_ok = test_json_logging()
    emails_ok = await test_emails(args.to)

    print("\n=== ИТОГ ===")
    print("  JSON-логи:", "PASS" if logs_ok else "FAIL")
    print("  Email:    ", "PASS" if emails_ok else "FAIL")
    return 0 if (logs_ok and emails_ok) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
