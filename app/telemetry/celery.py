"""Celery instrumentation — parent span (producer) -> child span (worker).

Call ``instrument_celery()`` from both the API process (when enqueuing) and the
worker process (in ``worker_process_init``) so the trace context propagates.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def instrument_celery() -> None:
    if not settings.OTEL_ENABLED:
        return
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
        logger.info("OTel instrumented: Celery")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Celery instrumentation skipped: %s", exc)
