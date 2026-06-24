"""PostgreSQL migration: appointments calendar tables."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent


def upgrade(engine: Engine) -> None:
    path = _MIGRATIONS_DIR / "027_add_appointments_tables.sql"
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied migration: 027_add_appointments_tables.sql")
