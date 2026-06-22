-- Phase 12b: DICOM ZIP archive support

ALTER TABLE dicom_studies ADD COLUMN zip_original_path TEXT;
ALTER TABLE dicom_studies ADD COLUMN zip_size_mb REAL;
ALTER TABLE dicom_studies ADD COLUMN total_files INTEGER NOT NULL DEFAULT 0;
ALTER TABLE dicom_studies ADD COLUMN processed_files INTEGER NOT NULL DEFAULT 0;

ALTER TABLE dicom_series ADD COLUMN original_filename VARCHAR(255);
