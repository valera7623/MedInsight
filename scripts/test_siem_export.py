#!/usr/bin/env python3
"""Test SIEM audit export: create event, sign, format, export (dry-run friendly)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import AuditLog  # noqa: E402
from app.services.audit_exporter import AuditExporter  # noqa: E402
from app.services.audit_formatter import AuditFormatter  # noqa: E402
from app.services.audit_signer import AuditSigner  # noqa: E402
from app.services.crypto_audit import CryptoAudit  # noqa: E402
from app.services.siem_target_manager import SiemTargetManager  # noqa: E402


def create_test_event(db) -> AuditLog:
    entry = AuditLog(
        user_id=1,
        tenant_id=1,
        action="audit.export.test",
        resource_type="siem_test",
        resource_id=None,
        ip_address="127.0.0.1",
        user_agent="test_siem_export/1.0",
        details={"test": True, "script": "test_siem_export.py"},
        export_status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    data = {
        "id": entry.id,
        "user_id": entry.user_id,
        "tenant_id": entry.tenant_id,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "ip_address": entry.ip_address,
        "user_agent": entry.user_agent,
        "details": entry.details,
        "created_at": entry.created_at,
    }
    entry.signature = AuditSigner.sign_event(data)
    entry.signed_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Test MedInsight SIEM audit export")
    parser.add_argument("--format", choices=["syslog", "cef", "splunk_hec", "jsonl"], default="jsonl")
    parser.add_argument("--target", default="sentinel")
    parser.add_argument("--send", action="store_true", help="Actually send to SIEM (default: format only)")
    args = parser.parse_args()

    print("=== MedInsight SIEM Export Test ===")
    print(f"SIEM_EXPORT_ENABLED={settings.SIEM_EXPORT_ENABLED}")
    print(f"AUDIT_SIGNING_ENABLED={settings.AUDIT_SIGNING_ENABLED}")

    CryptoAudit.generate_audit_key()

    db = SessionLocal()
    try:
        event = create_test_event(db)
        data = {
            "id": event.id,
            "user_id": event.user_id,
            "tenant_id": event.tenant_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
            "details": event.details,
            "created_at": event.created_at,
            "signature": event.signature,
        }
        verified = AuditSigner.verify_signature(data, event.signature or "")
        print(f"Event id={event.id} signature_valid={verified}")

        formatters = {
            "syslog": AuditFormatter.format_syslog,
            "cef": AuditFormatter.format_cef,
            "splunk_hec": lambda e: json.dumps(AuditFormatter.format_splunk_hec(e)),
            "jsonl": AuditFormatter.format_jsonl,
        }
        formatted = formatters[args.format](data)
        print(f"\n--- {args.format.upper()} preview ---")
        print(formatted if isinstance(formatted, str) else formatted)

        if args.send:
            target = SiemTargetManager.get_target(args.target)
            target["format"] = args.format
            connected = SiemTargetManager.test_connection(target)
            print(f"\nConnection test: {connected}")
            exporter = AuditExporter(db)
            try:
                ok = exporter.export_batch([event], args.format, target)
                print(f"Export result: {ok}")
            finally:
                exporter.close()
        else:
            print("\n(dry-run: pass --send to deliver to SIEM)")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
