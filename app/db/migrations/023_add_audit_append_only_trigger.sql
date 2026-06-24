-- Phase 13: PostgreSQL append-only trigger for audit_logs
-- Prevents UPDATE/DELETE on immutable audit records (export metadata updates
-- are handled at application layer; core event fields must never change).

CREATE OR REPLACE FUNCTION audit_logs_append_only()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit_logs is append-only: DELETE forbidden';
    ELSIF TG_OP = 'UPDATE' THEN
        -- Allow only export/signing metadata columns to change
        IF OLD.id IS DISTINCT FROM NEW.id
           OR OLD.user_id IS DISTINCT FROM NEW.user_id
           OR OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
           OR OLD.action IS DISTINCT FROM NEW.action
           OR OLD.resource_type IS DISTINCT FROM NEW.resource_type
           OR OLD.resource_id IS DISTINCT FROM NEW.resource_id
           OR OLD.ip_address IS DISTINCT FROM NEW.ip_address
           OR OLD.user_agent IS DISTINCT FROM NEW.user_agent
           OR OLD.details IS DISTINCT FROM NEW.details
           OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
            RAISE EXCEPTION 'audit_logs is append-only: core fields cannot be updated';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs;
CREATE TRIGGER trg_audit_logs_append_only
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION audit_logs_append_only();
