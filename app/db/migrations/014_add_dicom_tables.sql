-- Phase 12: DICOM medical imaging tables

CREATE TABLE IF NOT EXISTS dicom_studies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id          INTEGER      NOT NULL REFERENCES patients(id),
    tenant_id           INTEGER      NOT NULL REFERENCES tenants(id),
    user_id             INTEGER      NOT NULL REFERENCES users(id),
    study_uid           VARCHAR(128) NOT NULL UNIQUE,
    study_date          DATETIME,
    study_description   VARCHAR(500),
    modality            VARCHAR(16),
    body_part           VARCHAR(128),
    patient_name_dicom  VARCHAR(255),
    patient_id_dicom    VARCHAR(128),
    num_series          INTEGER      NOT NULL DEFAULT 0,
    num_instances       INTEGER      NOT NULL DEFAULT 0,
    file_path_encrypted TEXT,
    original_filename   VARCHAR(255),
    status              VARCHAR(20)  NOT NULL DEFAULT 'uploaded',
    error_message       TEXT,
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    processed_at        DATETIME
);

CREATE TABLE IF NOT EXISTS dicom_series (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    study_id            INTEGER      NOT NULL REFERENCES dicom_studies(id),
    series_uid          VARCHAR(128) NOT NULL UNIQUE,
    series_number       INTEGER,
    series_description  VARCHAR(500),
    modality            VARCHAR(16),
    num_instances       INTEGER      NOT NULL DEFAULT 0,
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dicom_frames (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id           INTEGER      NOT NULL REFERENCES dicom_series(id),
    instance_uid        VARCHAR(128) NOT NULL UNIQUE,
    frame_number        INTEGER      NOT NULL DEFAULT 0,
    image_path          TEXT         NOT NULL,
    width               INTEGER,
    height              INTEGER,
    bit_depth           INTEGER,
    pixel_spacing       JSON,
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_dicom_studies_patient_id ON dicom_studies (patient_id);
CREATE INDEX IF NOT EXISTS ix_dicom_studies_tenant_id ON dicom_studies (tenant_id);
CREATE INDEX IF NOT EXISTS ix_dicom_studies_study_uid ON dicom_studies (study_uid);
CREATE INDEX IF NOT EXISTS ix_dicom_series_study_id ON dicom_series (study_id);
CREATE INDEX IF NOT EXISTS ix_dicom_frames_series_id ON dicom_frames (series_id);
