-- Phase 13: audit event signing columns on audit_logs
-- Safe to run repeatedly (IF NOT EXISTS / conditional ALTER).

-- PostgreSQL
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS signature VARCHAR(64);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS signed_at TIMESTAMP;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS export_status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS export_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS last_export_attempt_at TIMESTAMP;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS export_error TEXT;

CREATE INDEX IF NOT EXISTS ix_audit_logs_export_status ON audit_logs (export_status);

-- SQLite (manual / documentation)
-- ALTER TABLE audit_logs ADD COLUMN signature VARCHAR(64);
-- ALTER TABLE audit_logs ADD COLUMN signed_at DATETIME;
-- ALTER TABLE audit_logs ADD COLUMN export_status VARCHAR(20) NOT NULL DEFAULT 'pending';
-- ALTER TABLE audit_logs ADD COLUMN export_attempts INTEGER NOT NULL DEFAULT 0;
-- ALTER TABLE audit_logs ADD COLUMN last_export_attempt_at DATETIME;
-- ALTER TABLE audit_logs ADD COLUMN export_error TEXT;
