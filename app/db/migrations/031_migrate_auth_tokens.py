"""Add token_version and TOTP columns to users (PostgreSQL)."""

from sqlalchemy import inspect, text


def upgrade(engine) -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "token_version" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
        if "totp_secret" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN totp_secret VARCHAR(255)"))
        if "totp_enabled" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
        if "totp_backup_codes" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN totp_backup_codes VARCHAR(1024)"))
