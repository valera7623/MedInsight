"""SIEM target configuration and connectivity tests."""

from __future__ import annotations

import logging
import socket
import ssl
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TARGET_PRESETS: dict[str, dict[str, Any]] = {
    "splunk": {
        "name": "splunk",
        "format": "splunk_hec",
        "url": settings.SPLUNK_HEC_URL,
        "token": settings.SPLUNK_HEC_TOKEN,
        "tls": True,
    },
    "sentinel": {
        "name": "sentinel",
        "format": "syslog",
        "host": settings.SIEM_EXPORT_HOST,
        "port": settings.SIEM_EXPORT_PORT,
        "tls": settings.SIEM_EXPORT_TLS,
        "tls_cert": settings.SIEM_EXPORT_TLS_CERT,
        "tls_key": settings.SIEM_EXPORT_TLS_KEY,
    },
    "log360": {
        "name": "log360",
        "format": "cef",
        "host": settings.SIEM_EXPORT_HOST,
        "port": settings.SIEM_EXPORT_PORT,
        "tls": settings.SIEM_EXPORT_TLS,
        "tls_cert": settings.SIEM_EXPORT_TLS_CERT,
        "tls_key": settings.SIEM_EXPORT_TLS_KEY,
    },
    "securonix": {
        "name": "securonix",
        "format": "syslog",
        "host": settings.SIEM_EXPORT_HOST,
        "port": settings.SIEM_EXPORT_PORT,
        "tls": settings.SIEM_EXPORT_TLS,
        "tls_cert": settings.SIEM_EXPORT_TLS_CERT,
        "tls_key": settings.SIEM_EXPORT_TLS_KEY,
    },
}


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if settings.SIEM_EXPORT_TLS_CERT and settings.SIEM_EXPORT_TLS_KEY:
        ctx.load_cert_chain(settings.SIEM_EXPORT_TLS_CERT, settings.SIEM_EXPORT_TLS_KEY)
    return ctx


class SiemTargetManager:
    """Resolve and validate SIEM export targets."""

    @classmethod
    def get_targets(cls) -> list[dict[str, Any]]:
        if not settings.SIEM_EXPORT_ENABLED:
            return []
        return [dict(t) for t in TARGET_PRESETS.values()]

    @classmethod
    def get_target(cls, name: str) -> dict[str, Any]:
        target = TARGET_PRESETS.get(name)
        if not target:
            raise KeyError(f"Unknown SIEM target: {name}")
        return dict(target)

    @classmethod
    def get_default_target(cls) -> dict[str, Any]:
        protocol = settings.SIEM_EXPORT_PROTOCOL
        format_map = {
            "syslog": "sentinel",
            "cef": "log360",
            "splunk_hec": "splunk",
            "jsonl": "sentinel",
        }
        name = format_map.get(protocol, "sentinel")
        target = cls.get_target(name)
        target["format"] = protocol
        target["host"] = settings.SIEM_EXPORT_HOST
        target["port"] = settings.SIEM_EXPORT_PORT
        target["tls"] = settings.SIEM_EXPORT_TLS
        return target

    @classmethod
    def test_connection(cls, target: dict[str, Any]) -> bool:
        fmt = target.get("format", settings.SIEM_EXPORT_PROTOCOL)
        try:
            if fmt == "splunk_hec":
                return cls._test_splunk(target)
            return cls._test_syslog(target)
        except Exception as exc:
            logger.warning("SIEM connection test failed for %s: %s", target.get("name"), exc)
            return False

    @staticmethod
    def _test_splunk(target: dict[str, Any]) -> bool:
        url = target.get("url") or settings.SPLUNK_HEC_URL
        token = target.get("token") or settings.SPLUNK_HEC_TOKEN
        if not url or not token:
            return False
        headers = {"Authorization": f"Splunk {token}"}
        with httpx.Client(timeout=5.0, verify=True) as client:
            resp = client.get(url.replace("/services/collector", "/services/collector/health"), headers=headers)
            return resp.status_code < 500

    @staticmethod
    def _test_syslog(target: dict[str, Any]) -> bool:
        host = target.get("host") or settings.SIEM_EXPORT_HOST
        port = int(target.get("port") or settings.SIEM_EXPORT_PORT)
        use_tls = bool(target.get("tls", settings.SIEM_EXPORT_TLS))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            if use_tls:
                ctx = _tls_context()
                with ctx.wrap_socket(sock, server_hostname=host) as tls_sock:
                    tls_sock.connect((host, port))
            else:
                sock.connect((host, port))
            return True
        finally:
            try:
                sock.close()
            except OSError:
                pass
