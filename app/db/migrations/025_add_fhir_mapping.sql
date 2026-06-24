-- Phase 14: FHIR resource ID mapping table
-- MedInsight also auto-creates via SQLAlchemy create_all on startup.

CREATE TABLE IF NOT EXISTS fhir_mapping (
    id              SERIAL PRIMARY KEY,
    resource_type   VARCHAR(50) NOT NULL,
    medinsight_id   INTEGER NOT NULL,
    fhir_id         VARCHAR(128) NOT NULL,
    fhir_version    VARCHAR(10) NOT NULL DEFAULT 'R4',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_fhir_mapping_resource_medinsight UNIQUE (resource_type, medinsight_id)
);

CREATE INDEX IF NOT EXISTS ix_fhir_mapping_resource_medinsight ON fhir_mapping (resource_type, medinsight_id);
CREATE INDEX IF NOT EXISTS ix_fhir_mapping_fhir_id ON fhir_mapping (fhir_id);
