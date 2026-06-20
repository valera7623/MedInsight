import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


def sqlite_db_path(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    path_str = url[len("sqlite:///"):]
    if path_str == ":memory:":
        return None
    return Path(path_str)


def ensure_db_directory() -> None:
    db_path = sqlite_db_path(settings.DATABASE_URL)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Database directory ready: %s", db_path.parent)


ensure_db_directory()

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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


def run_migrations():
    """Lightweight SQLite migrations (no Alembic)."""
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

        if "documents" in tables:
            _add_column_if_missing(conn, "documents", "is_encrypted", "BOOLEAN", "0")

        if "patients" in tables:
            _add_column_if_missing(conn, "patients", "department_id", "INTEGER")
            _add_column_if_missing(conn, "patients", "attending_doctor_id", "INTEGER")

        # Backfill NULL tenant_id for legacy rows
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


def bootstrap_system():
    """Create default tenant, super admin, and encryption key on first run."""
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
            )
            db.add(super_admin)
            db.commit()
            logger.info("Created super admin: %s", settings.SUPER_ADMIN_EMAIL)

        Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        Path(settings.STORAGE_PATH, "encrypted").mkdir(parents=True, exist_ok=True)
    finally:
        db.close()
