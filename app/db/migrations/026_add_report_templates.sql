-- Phase 15: PDF report templates
-- MedInsight also auto-creates via SQLAlchemy create_all on startup.

CREATE TABLE IF NOT EXISTS report_templates (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    template_type   VARCHAR(50) NOT NULL,
    template_html   TEXT NOT NULL,
    template_css    TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      INTEGER NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_report_templates_tenant_type ON report_templates (tenant_id, template_type);

CREATE TABLE IF NOT EXISTS report_template_variables (
    id                    SERIAL PRIMARY KEY,
    template_id           INTEGER NOT NULL REFERENCES report_templates(id) ON DELETE CASCADE,
    variable_name         VARCHAR(100) NOT NULL,
    variable_type         VARCHAR(20) NOT NULL DEFAULT 'text',
    variable_description  VARCHAR(512),
    is_required           BOOLEAN NOT NULL DEFAULT FALSE,
    default_value         TEXT
);

CREATE INDEX IF NOT EXISTS ix_report_template_variables_template ON report_template_variables (template_id);

CREATE TABLE IF NOT EXISTS generated_reports (
    id              SERIAL PRIMARY KEY,
    template_id     INTEGER NOT NULL REFERENCES report_templates(id),
    patient_id      INTEGER NOT NULL REFERENCES patients(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id),
    report_data     JSONB,
    pdf_path        TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS ix_generated_reports_patient_created ON generated_reports (patient_id, created_at);
CREATE INDEX IF NOT EXISTS ix_generated_reports_status ON generated_reports (status);
