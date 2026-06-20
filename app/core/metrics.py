"""Prometheus metrics.

Falls back to no-op stubs when ``prometheus_client`` is not installed, so the
application never hard-depends on the metrics stack.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

    PROMETHEUS_AVAILABLE = True
except Exception:  # noqa: BLE001
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class _NoopMetric:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def labels(self, *args, **kwargs) -> "_NoopMetric":
            return self

        def inc(self, *args, **kwargs) -> None:
            pass

        def set(self, *args, **kwargs) -> None:
            pass

    def Counter(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

    def Gauge(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

    def generate_latest(*args, **kwargs) -> bytes:  # type: ignore[misc]
        return b""

    logger.info("prometheus_client not installed — metrics are no-ops")


rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Number of requests rejected by rate limiting",
    ["endpoint", "ip_hash"],
)

health_status = Gauge(
    "health_status",
    "Readiness of a dependency (1 = healthy, 0 = unhealthy)",
    ["component"],
)


def render_metrics() -> bytes:
    return generate_latest()
