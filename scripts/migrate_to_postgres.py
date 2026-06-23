#!/usr/bin/env python3
"""Migrate data from SQLite to PostgreSQL.

Usage:
    python scripts/migrate_to_postgres.py \\
        --sqlite-url sqlite:////app/data/medinsight.db \\
        --postgres-url postgresql://medinsight:pass@postgres:5432/medinsight

Reads all rows from SQLite, writes to PostgreSQL preserving integer primary keys.
Run after ``create_all`` + migration 019 on an empty PostgreSQL database.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_to_postgres")

TABLE_ORDER = [
    "tenants",
    "departments",
    "users",
    "preferences",
    "patients",
    "documents",
    "analysis_jobs",
    "predictions",
    "audit_logs",
    "error_fixes",
    "webhooks",
    "subscriptions",
    "payments",
    "telegram_users",
    "dicom_studies",
    "dicom_series",
    "dicom_frames",
    "dicom_annotations",
    "dicom_annotation_sessions",
    "annotation_history",
    "backup_logs",
]

JSON_COLUMNS: dict[str, set[str]] = {
    "tenants": {"settings"},
    "preferences": {"settings"},
    "documents": {"parsed_data"},
    "analysis_jobs": {"result"},
    "predictions": {"features", "prediction", "probabilities"},
    "audit_logs": {"details"},
    "error_fixes": {"solution_code"},
    "webhooks": {"events"},
    "telegram_users": {"subscription_events"},
    "dicom_studies": {"radiology_findings", "extracted_measurements"},
    "dicom_frames": {"pixel_spacing"},
    "dicom_annotations": {"coordinates"},
    "annotation_history": {"before_state", "after_state"},
}


def _run_pg_migration(engine) -> None:
    migration_path = ROOT / "app" / "db" / "migrations" / "019_migrate_to_postgresql.py"
    spec = importlib.util.spec_from_file_location("migration_019", migration_path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.upgrade(engine)


def _parse_json_fields(table: str, row: dict) -> dict:
    cols = JSON_COLUMNS.get(table, set())
    out = dict(row)
    for col in cols:
        val = out.get(col)
        if isinstance(val, str):
            try:
                out[col] = json.loads(val)
            except json.JSONDecodeError:
                pass
    return out


def migrate(sqlite_url: str, postgres_url: str, batch_size: int = 500) -> dict[str, int]:
    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    dst_engine = create_engine(postgres_url, pool_pre_ping=True)

    src_inspector = inspect(src_engine)
    src_tables = set(src_inspector.get_table_names())
    dst_tables = set(inspect(dst_engine).get_table_names())

    if not dst_tables:
        logger.info("Target PostgreSQL is empty — creating schema from models …")
        from app.core.database import Base

        Base.metadata.create_all(bind=dst_engine)
        _run_pg_migration(dst_engine)
        dst_tables = set(inspect(dst_engine).get_table_names())

    counts: dict[str, int] = {}
    errors: list[str] = []

    with dst_engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))

    try:
        for table in TABLE_ORDER:
            if table not in src_tables:
                continue
            if table not in dst_tables:
                logger.warning("Skip %s (not in PostgreSQL)", table)
                continue

            columns = [c["name"] for c in src_inspector.get_columns(table)]
            if not columns:
                continue

            col_list = ", ".join(columns)
            placeholders = ", ".join(f":{c}" for c in columns)
            insert_sql = text(
                f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
            )

            offset = 0
            table_count = 0
            with src_engine.connect() as src_conn:
                while True:
                    rows = (
                        src_conn.execute(
                            text(f'SELECT {col_list} FROM "{table}" LIMIT :limit OFFSET :offset'),
                            {"limit": batch_size, "offset": offset},
                        )
                        .mappings()
                        .all()
                    )
                    if not rows:
                        break

                    with dst_engine.begin() as dst_conn:
                        for row in rows:
                            payload = _parse_json_fields(
                                table, {k: v for k, v in dict(row).items()}
                            )
                            try:
                                dst_conn.execute(insert_sql, payload)
                                table_count += 1
                            except Exception as exc:  # noqa: BLE001
                                errors.append(f"{table} id={payload.get('id')}: {exc}")

                    offset += batch_size

            counts[table] = table_count
            logger.info("Migrated %s: %d rows", table, table_count)

        with dst_engine.begin() as conn:
            for table in reversed(TABLE_ORDER):
                if table in counts and counts[table]:
                    seq = f"{table}_id_seq"
                    exists = conn.execute(
                        text("SELECT 1 FROM pg_class WHERE relname = :seq"),
                        {"seq": seq},
                    ).fetchone()
                    if exists:
                        conn.execute(
                            text(
                                f"SELECT setval('{seq}', "
                                f"COALESCE((SELECT MAX(id) FROM \"{table}\"), 1))"
                            )
                        )
    finally:
        with dst_engine.begin() as conn:
            conn.execute(text("SET session_replication_role = 'origin'"))

    _verify_integrity(src_engine, dst_engine, counts, errors)
    return counts


def _verify_integrity(src_engine, dst_engine, counts: dict[str, int], errors: list[str]) -> None:
    mismatches = []
    for table in counts:
        with dst_engine.connect() as conn:
            actual = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
        with src_engine.connect() as conn:
            source = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
        if actual < source:
            mismatches.append(f"{table}: source={source}, target={actual}")

    if mismatches:
        logger.error("Integrity check failed: %s", "; ".join(mismatches))
    else:
        logger.info("Integrity check passed for %d tables", len(counts))

    if errors:
        logger.error("%d row errors (first 5):", len(errors))
        for err in errors[:5]:
            logger.error("  %s", err)
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate MedInsight SQLite → PostgreSQL")
    parser.add_argument("--sqlite-url", default="sqlite:///./medinsight.db")
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    logger.info("Source: %s", args.sqlite_url)
    logger.info("Target: %s", args.postgres_url.split("@")[-1])

    counts = migrate(args.sqlite_url, args.postgres_url, args.batch_size)
    logger.info("Done — %d rows across %d tables", sum(counts.values()), len(counts))


if __name__ == "__main__":
    main()
