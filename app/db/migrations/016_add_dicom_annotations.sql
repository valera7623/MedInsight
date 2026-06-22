-- Phase 12c: DICOM frame annotations

CREATE TABLE IF NOT EXISTS dicom_annotations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id            INTEGER      NOT NULL REFERENCES dicom_frames(id) ON DELETE CASCADE,
    user_id             INTEGER      NOT NULL REFERENCES users(id),
    type                VARCHAR(32)  NOT NULL,
    coordinates         JSON         NOT NULL,
    color               VARCHAR(16)  NOT NULL DEFAULT '#FF0000',
    label               VARCHAR(255),
    measurement_value   REAL,
    measurement_unit    VARCHAR(16),
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    deleted_at          DATETIME
);

CREATE INDEX IF NOT EXISTS ix_dicom_annotations_frame_id ON dicom_annotations (frame_id);
CREATE INDEX IF NOT EXISTS ix_dicom_annotations_user_id ON dicom_annotations (user_id);
