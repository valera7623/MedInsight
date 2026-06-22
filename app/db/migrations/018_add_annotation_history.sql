-- Phase 12d: annotation edit history (undo/audit)

CREATE TABLE IF NOT EXISTS annotation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER      NOT NULL REFERENCES users(id),
    annotation_id   INTEGER      REFERENCES dicom_annotations(id) ON DELETE SET NULL,
    frame_id        INTEGER      NOT NULL REFERENCES dicom_frames(id) ON DELETE CASCADE,
    action          VARCHAR(32)  NOT NULL,
    before_state    JSON,
    after_state     JSON,
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_annotation_history_user_id ON annotation_history (user_id);
CREATE INDEX IF NOT EXISTS ix_annotation_history_frame_id ON annotation_history (frame_id);
CREATE INDEX IF NOT EXISTS ix_annotation_history_annotation_id ON annotation_history (annotation_id);
