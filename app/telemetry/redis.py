"""Redis instrumentation (db.operation / db.redis.database_index)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def instrument_redis() -> None:
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.info("OTel instrumented: Redis")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis instrumentation skipped: %s", exc)
