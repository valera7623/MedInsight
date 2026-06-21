"""FastAPI auto-instrumentation (spans per request)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def instrument_fastapi(app) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Don't trace noisy health/metrics probes.
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="health,health/live,health/ready,metrics"
        )
        logger.info("OTel instrumented: FastAPI")
    except Exception as exc:  # noqa: BLE001
        logger.debug("FastAPI instrumentation skipped: %s", exc)
