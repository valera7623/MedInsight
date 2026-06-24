-- Phase 13: SIEM export log tables
-- MedInsight also auto-creates via SQLAlchemy create_all on startup.

CREATE TABLE IF NOT EXISTS audit_export_logs (
    id              SERIAL PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES audit_logs(id) ON DELETE CASCADE,
    format          VARCHAR(20) NOT NULL,
    target          VARCHAR(50) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    response_code   INTEGER,
    response_body   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_export_logs_event_created ON audit_export_logs (event_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_export_logs_target_status ON audit_export_logs (target, status);

CREATE TABLE IF NOT EXISTS audit_keys (
    id              SERIAL PRIMARY KEY,
    key             TEXT NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_keys_active ON audit_keys (active);

-- SQLite variant (documentation)
-- CREATE TABLE IF NOT EXISTS audit_export_logs (...);
-- CREATE TABLE IF NOT EXISTS audit_keys (...);
