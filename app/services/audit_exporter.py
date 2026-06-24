"""Deliver audit events to external SIEM systems with retry and TLS 1.2+."""

from __future__ import annotations

import json
import logging
import socket
import ssl
import time
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import AuditExportLog, AuditLog
from app.services.audit_formatter import AuditFormatter
from app.services.audit_signer import AuditSigner
from app.services.siem_target_manager import SiemTargetManager

logger = logging.getLogger(__name__)


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if settings.SIEM_EXPORT_TLS_CERT and settings.SIEM_EXPORT_TLS_KEY:
        ctx.load_cert_chain(settings.SIEM_EXPORT_TLS_CERT, settings.SIEM_EXPORT_TLS_KEY)
    return ctx


def _event_to_dict(event: AuditLog | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, AuditLog):
        return {
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
            "signed_at": event.signed_at,
        }
    return dict(event)


class AuditExporter:
    """Export signed audit events to SIEM targets."""

    def __init__(self, db: Session | None = None) -> None:
        self._db = db
        self._owns_db = db is None

    def _session(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def close(self) -> None:
        if self._owns_db and self._db is not None:
            self._db.close()
            self._db = None

    def _record_export(
        self,
        db: Session,
        event_id: int,
        fmt: str,
        target_name: str,
        *,
        success: bool,
        response_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        log = AuditExportLog(
            event_id=event_id,
            format=fmt,
            target=target_name,
            status="success" if success else "failed",
            response_code=response_code,
            response_body=(response_body or "")[:2000] or None,
        )
        db.add(log)

    def _send_syslog_lines(self, lines: list[str], target: dict[str, Any]) -> tuple[bool, int | None, str | None]:
        host = target.get("host") or settings.SIEM_EXPORT_HOST
        port = int(target.get("port") or settings.SIEM_EXPORT_PORT)
        use_tls = bool(target.get("tls", settings.SIEM_EXPORT_TLS))
        payload = "\n".join(lines) + "\n"
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            if use_tls:
                ctx = _tls_context()
                with ctx.wrap_socket(sock, server_hostname=host) as tls_sock:
                    tls_sock.connect((host, port))
                    tls_sock.sendall(payload.encode("utf-8"))
            else:
                sock.connect((host, port))
                sock.sendall(payload.encode("utf-8"))
                sock.close()
            return True, 200, "ok"
        except Exception as exc:
            return False, None, str(exc)

    def export_to_syslog(self, events: list, target: dict[str, Any]) -> bool:
        lines = [AuditFormatter.format_syslog(_event_to_dict(e)) for e in events]
        ok, code, body = self._send_syslog_lines(lines, target)
        self._update_events(events, ok, target, "syslog", code, body)
        return ok

    def export_to_cef(self, events: list, target: dict[str, Any]) -> bool:
        lines = [AuditFormatter.format_cef(_event_to_dict(e)) for e in events]
        ok, code, body = self._send_syslog_lines(lines, target)
        self._update_events(events, ok, target, "cef", code, body)
        return ok

    def export_to_splunk_hec(self, events: list, target: dict[str, Any]) -> bool:
        url = target.get("url") or settings.SPLUNK_HEC_URL
        token = target.get("token") or settings.SPLUNK_HEC_TOKEN
        if not url or not token:
            self._update_events(events, False, target, "splunk_hec", None, "missing HEC URL or token")
            return False
        headers = {"Authorization": f"Splunk {token}", "Content-Type": "application/json"}
        bodies = [AuditFormatter.format_splunk_hec(_event_to_dict(e)) for e in events]
        ok_all = True
        last_code: int | None = None
        last_body: str | None = None
        try:
            with httpx.Client(timeout=15.0, verify=True) as client:
                for body in bodies:
                    resp = client.post(url, headers=headers, content=json.dumps(body))
                    last_code = resp.status_code
                    last_body = resp.text[:500]
                    if not (200 <= resp.status_code < 300):
                        ok_all = False
        except Exception as exc:
            ok_all = False
            last_body = str(exc)
        self._update_events(events, ok_all, target, "splunk_hec", last_code, last_body)
        return ok_all

    def export_to_jsonl(self, events: list, target: dict[str, Any]) -> bool:
        from pathlib import Path

        archive_dir = Path(settings.AUDIT_JSONL_ARCHIVE_DIR)
        archive_dir.mkdir(parents=True, exist_ok=True)
        target_name = target.get("name", "jsonl")
        out_path = archive_dir / f"export_{target_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"
        try:
            with out_path.open("w", encoding="utf-8") as fh:
                for event in events:
                    fh.write(AuditFormatter.format_jsonl(_event_to_dict(event)) + "\n")
            ok = True
            code, body = 200, str(out_path)
        except Exception as exc:
            ok = False
            code, body = None, str(exc)
        self._update_events(events, ok, target, "jsonl", code, body)
        return ok

    def export_batch(self, events: list, fmt: str, target: dict[str, Any]) -> bool:
        exporters = {
            "syslog": self.export_to_syslog,
            "cef": self.export_to_cef,
            "splunk_hec": self.export_to_splunk_hec,
            "jsonl": self.export_to_jsonl,
        }
        handler = exporters.get(fmt)
        if not handler:
            raise ValueError(f"Unsupported export format: {fmt}")
        verified = []
        for event in events:
            data = _event_to_dict(event)
            sig = data.get("signature")
            if sig and not AuditSigner.verify_signature(data, sig):
                logger.warning("Skipping audit event %s: invalid signature", data.get("id"))
                continue
            verified.append(event)
        if not verified:
            return False
        return handler(verified, target)

    def _update_events(
        self,
        events: list,
        success: bool,
        target: dict[str, Any],
        fmt: str,
        response_code: int | None,
        response_body: str | None,
    ) -> None:
        db = self._session()
        target_name = target.get("name", "default")
        for event in events:
            event_id = event.id if isinstance(event, AuditLog) else event.get("id")
            if event_id is None:
                continue
            row = db.get(AuditLog, event_id)
            if not row:
                continue
            row.export_attempts = (row.export_attempts or 0) + 1
            row.last_export_attempt_at = datetime.utcnow()
            if success:
                row.export_status = "exported"
                row.export_error = None
            else:
                row.export_status = "failed"
                row.export_error = (response_body or "export failed")[:1000]
            self._record_export(
                db,
                event_id,
                fmt,
                target_name,
                success=success,
                response_code=response_code,
                response_body=response_body,
            )
        db.commit()

    def retry_failed_events(self) -> int:
        if not settings.SIEM_EXPORT_ENABLED:
            return 0
        db = self._session()
        target = SiemTargetManager.get_default_target()
        fmt = target.get("format", settings.SIEM_EXPORT_PROTOCOL)
        batch_size = settings.SIEM_EXPORT_BATCH_SIZE
        max_attempts = settings.SIEM_EXPORT_RETRY_COUNT
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.export_status == "failed", AuditLog.export_attempts < max_attempts)
            .order_by(AuditLog.id.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            return 0
        delay = 1.0
        retried = 0
        for attempt in range(1, max_attempts + 1):
            if not rows:
                break
            ok = self.export_batch(rows, fmt, target)
            retried += len(rows)
            if ok:
                break
            time.sleep(delay)
            delay *= 2
            rows = (
                db.query(AuditLog)
                .filter(AuditLog.export_status == "failed", AuditLog.export_attempts < max_attempts)
                .order_by(AuditLog.id.asc())
                .limit(batch_size)
                .all()
            )
        return retried
