"""Database engine, sessions, and dialect-aware migrations.

Development / tests: SQLite (``DATABASE_URL`` or ``DEVELOPMENT_DATABASE_URL``).
Production: PostgreSQL (``PRODUCTION_DATABASE_URL`` or ``DATABASE_URL``).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

logger = logging.getLogger(__name__)
sql_logger = logging.getLogger("app.database.sql")


def is_sqlite(url: str | None = None) -> bool:
    return (url or settings.DATABASE_URL).startswith("sqlite")


def is_postgresql(url: str | None = None) -> bool:
    url = url or settings.DATABASE_URL
    return url.startswith("postgresql") or url.startswith("postgres")


def sqlite_db_path(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    path_str = url[len("sqlite:///") :]
    if path_str == ":memory:":
        return None
    return Path(path_str)


def ensure_db_directory() -> None:
    if not is_sqlite():
        return
    db_path = sqlite_db_path(settings.DATABASE_URL)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Database directory ready: %s", db_path.parent)


def _is_sqlite_memory(url: str) -> bool:
    if not url.startswith("sqlite"):
        return False
    path = url[len("sqlite:///") :]
    return path in ("", ":memory:")


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {}
    if is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
        if _is_sqlite_memory(url):
            kwargs["poolclass"] = StaticPool
    elif is_postgresql(url):
        kwargs.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
        )
    return kwargs


ensure_db_directory()

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "before_cursor_execute")
def _sql_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("_query_start", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _sql_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    stack = conn.info.get("_query_start")
    if not stack:
        return
    duration_ms = (time.perf_counter() - stack.pop()) * 1000
    compact = " ".join(statement.split())
    if len(compact) > 500:
        compact = compact[:500] + "…"
    threshold = settings.LOG_SLOW_QUERY_MS
    if threshold and duration_ms >= threshold:
        sql_logger.warning(
            "Slow SQL query: %.1fms | %s",
            duration_ms,
            compact,
            extra={"duration_ms": round(duration_ms, 1)},
        )
    else:
        sql_logger.debug("SQL query: %.1fms | %s", duration_ms, compact)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def close_db_connection() -> None:
    """Dispose the SQLAlchemy engine and its connection pool (graceful shutdown)."""
    try:
        engine.dispose()
        logger.info("Database engine disposed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error disposing database engine: %s", exc)


def _add_column_if_missing(conn, table: str, column: str, col_type: str, default: str | None = None):
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns(table)}
    if column not in columns:
        default_clause = f" DEFAULT {default}" if default is not None else ""
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"))


def _run_sqlite_migrations():
    """Lightweight SQLite ALTER TABLE migrations (no Alembic)."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    with engine.begin() as conn:
        if "patients" in tables:
            _add_column_if_missing(conn, "patients", "middle_name", "VARCHAR(100)")
            _add_column_if_missing(conn, "patients", "tenant_id", "INTEGER", "1")

        for table in ("users", "documents", "predictions", "analysis_jobs"):
            if table in tables:
                _add_column_if_missing(conn, table, "tenant_id", "INTEGER", "1")

        if "users" in tables:
            _add_column_if_missing(conn, "users", "is_blocked", "BOOLEAN", "0")
            _add_column_if_missing(conn, "users", "department_id", "INTEGER")
            _add_column_if_missing(conn, "users", "can_see_all_patients", "BOOLEAN", "0")
            _add_column_if_missing(conn, "users", "email_verified", "BOOLEAN", "1")
            _add_column_if_missing(conn, "users", "email_verified_at", "DATETIME")
            _add_column_if_missing(conn, "users", "token_version", "INTEGER", "0")
            _add_column_if_missing(conn, "users", "totp_secret", "VARCHAR(255)")
            _add_column_if_missing(conn, "users", "totp_enabled", "BOOLEAN", "0")
            _add_column_if_missing(conn, "users", "totp_backup_codes", "VARCHAR(1024)")

        if "documents" in tables:
            _add_column_if_missing(conn, "documents", "is_encrypted", "BOOLEAN", "0")
            _add_column_if_missing(conn, "documents", "parsed_by_ai", "BOOLEAN", "0")
            _add_column_if_missing(conn, "documents", "parse_confidence", "REAL")

        if "patients" in tables:
            _add_column_if_missing(conn, "patients", "department_id", "INTEGER")
            _add_column_if_missing(conn, "patients", "attending_doctor_id", "INTEGER")
            _add_column_if_missing(conn, "patients", "search_vector", "TEXT")

        for table in ("tenants", "users", "patients", "documents"):
            if table in tables:
                _add_column_if_missing(conn, table, "public_id", "VARCHAR(36)")

        if "documents" in tables:
            _add_column_if_missing(conn, "documents", "search_vector", "TEXT")

        if "dicom_studies" in tables:
            _add_column_if_missing(conn, "dicom_studies", "search_vector", "TEXT")

        if "dicom_studies" in tables:
            _add_column_if_missing(conn, "dicom_studies", "zip_original_path", "TEXT")
            _add_column_if_missing(conn, "dicom_studies", "zip_size_mb", "REAL")
            _add_column_if_missing(conn, "dicom_studies", "total_files", "INTEGER", "0")
            _add_column_if_missing(conn, "dicom_studies", "processed_files", "INTEGER", "0")
            _add_column_if_missing(conn, "dicom_studies", "radiology_findings", "JSON")
            _add_column_if_missing(conn, "dicom_studies", "radiology_impression", "TEXT")
            _add_column_if_missing(conn, "dicom_studies", "extracted_measurements", "JSON")
            _add_column_if_missing(conn, "dicom_studies", "clinical_context", "TEXT")
            _add_column_if_missing(conn, "dicom_studies", "clinical_context_processed_at", "DATETIME")

        if "dicom_series" in tables:
            _add_column_if_missing(conn, "dicom_series", "original_filename", "VARCHAR(255)")

        if "users" in tables and "tenants" in tables:
            conn.execute(
                text(
                    "UPDATE users SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1) "
                    "WHERE tenant_id IS NULL AND role != 'super_admin'"
                )
            )
        if "patients" in tables and "tenants" in tables:
            conn.execute(
                text(
                    "UPDATE patients SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1) "
                    "WHERE tenant_id IS NULL"
                )
            )

        if "audit_logs" in tables:
            _add_column_if_missing(conn, "audit_logs", "signature", "VARCHAR(64)")
            _add_column_if_missing(conn, "audit_logs", "signed_at", "DATETIME")
            _add_column_if_missing(conn, "audit_logs", "export_status", "VARCHAR(20)", "'pending'")
            _add_column_if_missing(conn, "audit_logs", "export_attempts", "INTEGER", "0")
            _add_column_if_missing(conn, "audit_logs", "last_export_attempt_at", "DATETIME")
            _add_column_if_missing(conn, "audit_logs", "export_error", "TEXT")


def run_migrations():
    """Apply dialect-specific schema migrations after ``create_all``."""
    if is_sqlite():
        _run_sqlite_migrations()
    elif is_postgresql():
        import importlib.util
        from pathlib import Path

        migrations_dir = Path(__file__).resolve().parent.parent / "db" / "migrations"
        for migration_file in (
            "019_migrate_to_postgresql.py",
            "024_migrate_audit_siem.py",
            "025_migrate_fhir.py",
            "026_migrate_reports.py",
            "027_migrate_appointments.py",
            "028_migrate_cache_versions.py",
            "029_migrate_cache_stats.py",
            "030_migrate_ai_parser.py",
            "031_migrate_auth_tokens.py",
            "032_enterprise_rls.py",
        ):
            migration_path = migrations_dir / migration_file
            spec = importlib.util.spec_from_file_location(migration_file.replace(".py", ""), migration_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.upgrade(engine)
    else:
        logger.warning("Unknown database dialect for URL: %s", settings.DATABASE_URL.split("://")[0])


def bootstrap_system():
    """Create default tenant, super admin, and encryption key on first run."""
    from datetime import datetime

    from app.auth import hash_password
    from app.models import Tenant, User
    from app.services.encryption import ensure_encryption_key

    db = SessionLocal()
    try:
        ensure_encryption_key()

        tenant = db.query(Tenant).filter(Tenant.subdomain == settings.DEFAULT_TENANT_SUBDOMAIN).first()
        if not tenant:
            tenant = Tenant(
                name=settings.DEFAULT_TENANT_NAME,
                subdomain=settings.DEFAULT_TENANT_SUBDOMAIN,
                settings={},
                is_active=True,
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            logger.info("Created default tenant: %s", tenant.subdomain)

        super_admin = db.query(User).filter(User.email == settings.SUPER_ADMIN_EMAIL).first()
        if not super_admin:
            super_admin = User(
                tenant_id=None,
                email=settings.SUPER_ADMIN_EMAIL,
                password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
                full_name="Super Admin",
                role="super_admin",
                email_verified=True,
                email_verified_at=datetime.utcnow(),
            )
            db.add(super_admin)
            db.commit()
            logger.info("Created super admin: %s", settings.SUPER_ADMIN_EMAIL)

        Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        Path(settings.STORAGE_PATH, "encrypted").mkdir(parents=True, exist_ok=True)
    finally:
        db.close()
