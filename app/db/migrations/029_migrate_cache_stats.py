"""PostgreSQL migration: cache_stats table."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent


def upgrade(engine: Engine) -> None:
    path = _MIGRATIONS_DIR / "029_add_cache_stats.sql"
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied migration: 029_add_cache_stats.sql")
