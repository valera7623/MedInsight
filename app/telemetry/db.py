"""SQLAlchemy instrumentation (db.statement / db.operation / db.system)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def instrument_db(engine=None) -> None:
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        if engine is not None:
            SQLAlchemyInstrumentor().instrument(engine=engine, enable_commenter=True)
        else:
            SQLAlchemyInstrumentor().instrument(enable_commenter=True)
        logger.info("OTel instrumented: SQLAlchemy")
    except Exception as exc:  # noqa: BLE001
        logger.debug("SQLAlchemy instrumentation skipped: %s", exc)
