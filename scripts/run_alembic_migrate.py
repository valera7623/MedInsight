#!/usr/bin/env python3
"""Run Alembic migrations with optional PostgreSQL advisory lock."""

from __future__ import annotations

import subprocess
import sys

from sqlalchemy import text

from app.config import settings
from app.core.database import engine, is_postgresql


def main() -> int:
    lock_id = 987654321
    conn = engine.connect()
    trans = conn.begin()
    try:
        if is_postgresql():
            conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": lock_id})
        trans.commit()
    except Exception:
        trans.rollback()
        raise

    try:
        result = subprocess.run(["alembic", "upgrade", "head"], check=False)
        return result.returncode
    finally:
        if is_postgresql():
            conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
        conn.close()


if __name__ == "__main__":
    if not settings.ALEMBIC_ENABLED:
        print("ALEMBIC_ENABLED=false — skipping alembic upgrade")
        sys.exit(0)
    sys.exit(main())
