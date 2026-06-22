-- Phase 12c: DICOM annotation sessions

CREATE TABLE IF NOT EXISTS dicom_annotation_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER      NOT NULL REFERENCES users(id),
    study_uid           VARCHAR(128) NOT NULL,
    series_uid          VARCHAR(128) NOT NULL,
    frame_instance_uid  VARCHAR(128) NOT NULL,
    opened_at           DATETIME     DEFAULT CURRENT_TIMESTAMP,
    closed_at           DATETIME
);

CREATE INDEX IF NOT EXISTS ix_dicom_annotation_sessions_user_id ON dicom_annotation_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_dicom_annotation_sessions_study_uid ON dicom_annotation_sessions (study_uid);
