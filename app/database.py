"""Backward-compatible re-exports — prefer ``app.core.database`` for new code."""

from app.core.database import (  # noqa: F401
    Base,
    SessionLocal,
    bootstrap_system,
    close_db_connection,
    engine,
    ensure_db_directory,
    get_db,
    is_postgresql,
    is_sqlite,
    run_migrations,
    sqlite_db_path,
)

__all__ = [
    "Base",
    "SessionLocal",
    "bootstrap_system",
    "close_db_connection",
    "engine",
    "ensure_db_directory",
    "get_db",
    "is_postgresql",
    "is_sqlite",
    "run_migrations",
    "sqlite_db_path",
]
