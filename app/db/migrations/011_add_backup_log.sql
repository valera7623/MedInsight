-- Phase 8: backup logs
-- Note: MedInsight auto-creates tables via SQLAlchemy `Base.metadata.create_all`
-- on startup, so this file documents the schema and supports manual/SQL-based
-- provisioning. Safe to run repeatedly (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS backup_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_id         VARCHAR(255) NOT NULL UNIQUE,
    type              VARCHAR(20)  NOT NULL,            -- full | db | storage
    status            VARCHAR(20)  NOT NULL DEFAULT 'pending', -- pending|completed|failed
    path              TEXT,
    size_bytes        INTEGER      NOT NULL DEFAULT 0,
    duration_seconds  REAL         NOT NULL DEFAULT 0.0,
    contains_db       BOOLEAN      NOT NULL DEFAULT 0,
    contains_storage  BOOLEAN      NOT NULL DEFAULT 0,
    contains_config   BOOLEAN      NOT NULL DEFAULT 0,
    error_message     TEXT,
    created_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    completed_at      DATETIME
);

CREATE INDEX IF NOT EXISTS ix_backup_logs_backup_id ON backup_logs (backup_id);
CREATE INDEX IF NOT EXISTS ix_backup_logs_created_at ON backup_logs (created_at);
