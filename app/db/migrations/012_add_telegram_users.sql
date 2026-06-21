-- Phase 10: Telegram user linking for notifications
-- Auto-created via SQLAlchemy on startup; safe to run manually.

CREATE TABLE IF NOT EXISTS telegram_users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER      NOT NULL REFERENCES users(id),
    telegram_user_id    INTEGER      NOT NULL UNIQUE,
    telegram_username   VARCHAR(255),
    first_name          VARCHAR(255) NOT NULL DEFAULT '',
    last_name           VARCHAR(255),
    is_active           BOOLEAN      NOT NULL DEFAULT 1,
    subscription_events JSON         NOT NULL DEFAULT '["prediction.ready", "analysis.completed"]',
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_telegram_users_user_id ON telegram_users (user_id);
CREATE INDEX IF NOT EXISTS ix_telegram_users_telegram_user_id ON telegram_users (telegram_user_id);
