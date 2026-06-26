"""Prometheus metrics.

Falls back to no-op stubs when ``prometheus_client`` is not installed, so the
application never hard-depends on the metrics stack.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

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

        def observe(self, *args, **kwargs) -> None:
            pass

    def Counter(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

    def Gauge(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

    def Histogram(*args, **kwargs):  # type: ignore[misc]
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

# --- Phase 8: backup metrics ---
backup_size_bytes = Gauge(
    "backup_size_bytes",
    "Size in bytes of the most recent backup",
    ["type"],
)

backup_duration_seconds = Histogram(
    "backup_duration_seconds",
    "Backup duration in seconds",
    ["type"],
)

backup_status_total = Counter(
    "backup_status_total",
    "Backup outcomes",
    ["type", "result"],  # result = success | failure
)

backup_age_days = Gauge(
    "backup_age_days",
    "Age in days of the most recent successful backup",
)

# --- Phase 9: WebSocket + OpenTelemetry metrics ---
websocket_connections_total = Gauge(
    "websocket_connections_total",
    "Number of currently open WebSocket connections",
)

websocket_messages_sent_total = Counter(
    "websocket_messages_sent_total",
    "WebSocket messages pushed to clients",
)

websocket_messages_received_total = Counter(
    "websocket_messages_received_total",
    "WebSocket messages received from clients",
)

otel_spans_exported_total = Counter(
    "otel_spans_exported_total",
    "Spans successfully exported to the OTLP collector",
)

otel_spans_dropped_total = Counter(
    "otel_spans_dropped_total",
    "Spans dropped (export failure / sampling buffer overflow)",
)

# --- Phase 19: Redis cache metrics ---
cache_hits_total = Counter(
    "cache_hits_total",
    "Redis cache hits",
    ["layer"],  # sync | async
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Redis cache misses",
    ["layer"],
)

cache_size_bytes = Gauge(
    "cache_size_bytes",
    "Size of the last cached value written (approximate)",
)

cache_hit_rate = Gauge(
    "cache_hit_rate",
    "Rolling cache hit rate (0-1); alert if < 0.5",
)


def record_cache_hit(layer: str = "sync") -> None:
    cache_hits_total.labels(layer=layer).inc()
    _update_hit_rate()


def record_cache_miss(layer: str = "sync") -> None:
    cache_misses_total.labels(layer=layer).inc()
    _update_hit_rate()


def record_cache_set(size_bytes: int) -> None:
    cache_size_bytes.set(size_bytes)


def _update_hit_rate() -> None:
    if not PROMETHEUS_AVAILABLE:
        return
    try:
        hits = sum(s.value for s in cache_hits_total.collect()[0].samples)  # type: ignore[index]
        misses = sum(s.value for s in cache_misses_total.collect()[0].samples)  # type: ignore[index]
        total = hits + misses
        if total > 0:
            cache_hit_rate.set(hits / total)
    except Exception:  # noqa: BLE001
        pass


def render_metrics() -> bytes:
    return generate_latest()
