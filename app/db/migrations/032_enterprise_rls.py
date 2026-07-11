"""Enterprise: optional PostgreSQL RLS policies."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import settings

logger = logging.getLogger(__name__)

RLS_TABLES = ("patients", "documents", "audit_logs")


def apply_rls_policies(engine: Engine) -> None:
    if not settings.RLS_ENABLED:
        return
    url = str(engine.url)
    if not url.startswith("postgresql"):
        logger.info("RLS skipped (not PostgreSQL)")
        return
    with engine.begin() as conn:
        for table in RLS_TABLES:
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
            conn.execute(
                text(
                    f"""
                    CREATE POLICY tenant_isolation ON {table}
                    USING (
                        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int
                        OR current_setting('app.bypass_rls', true) = 'true'
                    )
                    """
                )
            )
    logger.info("RLS policies applied to %s", ", ".join(RLS_TABLES))


def upgrade(engine) -> None:
    apply_rls_policies(engine)
