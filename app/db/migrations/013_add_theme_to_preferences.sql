-- Phase 11: user preferences (theme / dark mode)
-- Auto-created via SQLAlchemy on startup; safe to run manually.

CREATE TABLE IF NOT EXISTS preferences (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER      NOT NULL UNIQUE REFERENCES users(id),
    theme         VARCHAR(20)  NOT NULL DEFAULT 'light',
    system_theme  BOOLEAN      NOT NULL DEFAULT 1,
    settings      JSON         DEFAULT '{}',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_preferences_user_id ON preferences (user_id);
