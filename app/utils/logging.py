"""Structured logging setup (structlog) for the whole application.

``configure_logging()`` wires structlog AND the stdlib ``logging`` module
through one pipeline, so library logs (uvicorn, sqlalchemy, celery, ...) and
``structlog.get_logger(...)`` calls all render the same way:

* ``LOG_JSON_FORMAT=true``  -> one JSON object per line (ELK / Loki friendly)
* ``LOG_JSON_FORMAT=false`` -> coloured, human-readable console output (dev)

Request-scoped fields (``request_id``, ``user_id``, ``tenant_id``, ``ip``,
``user_agent``) are merged automatically from contextvars.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.config import settings

_configured = False


def _shared_processors() -> list:
    """Processors applied to BOTH structlog and stdlib-routed records."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.EventRenamer("message"),
    ]


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    json_mode = settings.LOG_JSON_FORMAT
    shared = _shared_processors()

    renderer: structlog.types.Processor
    if json_mode:
        renderer = structlog.processors.JSONRenderer()
    else:
        # Console renderer expects the event under "event", not "message".
        renderer = structlog.dev.ConsoleRenderer(event_key="message")

    # structlog → stdlib handoff
    structlog.configure(
        processors=shared + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # foreign_pre_chain runs on records coming from stdlib loggers.
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())

    # Tame noisy libraries; let access logging flow through our middleware instead.
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    for lib in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(lib)
        lg.handlers.clear()
        lg.propagate = True

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger; configures logging lazily on first use."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)
