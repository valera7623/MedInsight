"""Format audit events for SIEM targets (Syslog, CEF, Splunk HEC, JSONL)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.config import settings

_PII_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PII_PHONE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")


def _redact_pii(value: str | None) -> str | None:
    if not value:
        return value
    value = _PII_EMAIL.sub("[REDACTED_EMAIL]", value)
    value = _PII_PHONE.sub("[REDACTED_PHONE]", value)
    return value


def _anonymize_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:4] + ["0000"] * max(0, len(parts) - 4))
    octets = ip.split(".")
    if len(octets) == 4:
        return f"{octets[0]}.{octets[1]}.0.0"
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    safe = dict(event)
    safe["ip_address"] = _anonymize_ip(event.get("ip_address"))
    safe["user_agent"] = _redact_pii(event.get("user_agent"))
    if isinstance(safe.get("details"), dict):
        details = json.loads(json.dumps(safe["details"], default=str))
        for key in list(details.keys()):
            if key in ("email", "phone", "full_name", "patient_name"):
                details[key] = "[REDACTED]"
            elif isinstance(details[key], str):
                details[key] = _redact_pii(details[key])
        safe["details"] = details
    return safe


class AuditFormatter:
    """Convert audit events to SIEM wire formats."""

    @staticmethod
    def get_cef_vendor() -> str:
        return settings.SIEM_EXPORT_CEF_VENDOR

    @staticmethod
    def get_cef_product() -> str:
        return settings.SIEM_EXPORT_CEF_PRODUCT

    @classmethod
    def format_syslog(cls, event: dict[str, Any]) -> str:
        safe = _sanitize_event(event)
        ts = safe.get("created_at") or datetime.now(timezone.utc)
        if isinstance(ts, str):
            ts_str = ts
        else:
            ts_str = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        msg = json.dumps(safe, separators=(",", ":"), default=str, ensure_ascii=False)
        # RFC 5424: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
        pri = 13 * 8 + 6  # local0.info
        hostname = "medinsight"
        app_name = "audit"
        msg_id = safe.get("action", "audit")
        return f"<{pri}>1 {ts_str} {hostname} {app_name} - {msg_id} - {msg}"

    @classmethod
    def format_cef(cls, event: dict[str, Any]) -> str:
        safe = _sanitize_event(event)
        vendor = cls.get_cef_vendor()
        product = cls.get_cef_product()
        version = "1.0"
        signature_id = safe.get("action", "audit")
        name = f"MedInsight {signature_id}"
        severity = 3
        extensions = [
            f"rt={safe.get('created_at', '')}",
            f"suser={safe.get('user_id', '')}",
            f"cs1={safe.get('tenant_id', '')}",
            f"cs1Label=tenant_id",
            f"cs2={safe.get('resource_type', '')}",
            f"cs2Label=resource_type",
            f"cs3={safe.get('resource_id', '')}",
            f"cs3Label=resource_id",
            f"src={safe.get('ip_address', '')}",
            f"msg={json.dumps(safe.get('details') or {}, default=str)[:512]}",
        ]
        if safe.get("signature"):
            extensions.append(f"cs4={safe['signature']}")
            extensions.append("cs4Label=event_signature")
        ext = " ".join(extensions)
        return f"CEF:0|{vendor}|{product}|{version}|{signature_id}|{name}|{severity}|{ext}"

    @classmethod
    def format_splunk_hec(cls, event: dict[str, Any]) -> dict[str, Any]:
        safe = _sanitize_event(event)
        return {
            "time": _to_epoch(safe.get("created_at")),
            "host": "medinsight",
            "source": "medinsight:audit",
            "sourcetype": "medinsight:audit:json",
            "event": safe,
        }

    @classmethod
    def format_jsonl(cls, event: dict[str, Any]) -> str:
        safe = _sanitize_event(event)
        return json.dumps(safe, separators=(",", ":"), default=str, ensure_ascii=False)


def _to_epoch(value: Any) -> float:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return datetime.now(timezone.utc).timestamp()
