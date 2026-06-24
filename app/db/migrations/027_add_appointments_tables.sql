-- Phase 16: Appointments calendar
-- MedInsight also auto-creates via SQLAlchemy create_all on startup.

CREATE TABLE IF NOT EXISTS appointment_types (
    id                  SERIAL PRIMARY KEY,
    tenant_id           INTEGER NOT NULL REFERENCES tenants(id),
    name                VARCHAR(255) NOT NULL,
    code                VARCHAR(64) NOT NULL,
    duration_minutes      INTEGER NOT NULL DEFAULT 30,
    color               VARCHAR(16) NOT NULL DEFAULT '#3B82F6',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_appointment_type_tenant_code UNIQUE (tenant_id, code)
);

CREATE INDEX IF NOT EXISTS ix_appointment_types_tenant_active ON appointment_types (tenant_id, is_active);

CREATE TABLE IF NOT EXISTS appointments (
    id                      SERIAL PRIMARY KEY,
    tenant_id               INTEGER NOT NULL REFERENCES tenants(id),
    patient_id              INTEGER NOT NULL REFERENCES patients(id),
    doctor_id               INTEGER NOT NULL REFERENCES users(id),
    created_by              INTEGER NOT NULL REFERENCES users(id),
    appointment_type_id     INTEGER NOT NULL REFERENCES appointment_types(id),
    status                  VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    start_time              TIMESTAMP NOT NULL,
    end_time                TIMESTAMP NOT NULL,
    duration_minutes        INTEGER NOT NULL DEFAULT 30,
    title                   VARCHAR(500) NOT NULL,
    description             TEXT,
    notes                   TEXT,
    patient_document_id     INTEGER REFERENCES documents(id),
    dicom_study_id          INTEGER REFERENCES dicom_studies(id),
    prediction_id           INTEGER REFERENCES predictions(id),
    remind_before_minutes   INTEGER NOT NULL DEFAULT 30,
    reminder_sent           BOOLEAN NOT NULL DEFAULT FALSE,
    reminder_sent_at        TIMESTAMP,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cancelled_at            TIMESTAMP,
    cancelled_by            INTEGER REFERENCES users(id),
    cancellation_reason     TEXT
);

CREATE INDEX IF NOT EXISTS ix_appointments_doctor_start ON appointments (doctor_id, start_time);
CREATE INDEX IF NOT EXISTS ix_appointments_patient_start ON appointments (patient_id, start_time);
CREATE INDEX IF NOT EXISTS ix_appointments_tenant_status ON appointments (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_appointments_start_time ON appointments (start_time);

CREATE TABLE IF NOT EXISTS appointment_recurring (
    id                  SERIAL PRIMARY KEY,
    tenant_id           INTEGER NOT NULL REFERENCES tenants(id),
    appointment_id      INTEGER NOT NULL UNIQUE REFERENCES appointments(id) ON DELETE CASCADE,
    recurrence_type     VARCHAR(32) NOT NULL DEFAULT 'weekly',
    recurrence_interval INTEGER NOT NULL DEFAULT 1,
    recurrence_days     JSONB,
    recurrence_until    DATE,
    recurrence_count    INTEGER,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_appointment_recurring_tenant ON appointment_recurring (tenant_id);

CREATE TABLE IF NOT EXISTS appointment_history (
    id                  SERIAL PRIMARY KEY,
    appointment_id      INTEGER NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    previous_status     VARCHAR(32) NOT NULL,
    new_status          VARCHAR(32) NOT NULL,
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_appointment_history_appointment ON appointment_history (appointment_id);
