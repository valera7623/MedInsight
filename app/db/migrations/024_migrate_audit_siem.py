"""PostgreSQL migration: SIEM audit export schema + append-only trigger."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent


def _run_sql_file(engine: Engine, filename: str) -> None:
    path = _MIGRATIONS_DIR / filename
    if not path.exists():
        logger.warning("Migration file missing: %s", path)
        return
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied migration: %s", filename)


def upgrade(engine: Engine) -> None:
    _run_sql_file(engine, "021_add_audit_signing.sql")
    _run_sql_file(engine, "022_add_audit_export_tables.sql")
    _run_sql_file(engine, "023_add_audit_append_only_trigger.sql")
