-- Phase 12e: DICOM clinical context for GPT predictions
-- Note: processed_at already exists for DICOM ingest completion.

ALTER TABLE dicom_studies ADD COLUMN radiology_findings JSON;
ALTER TABLE dicom_studies ADD COLUMN radiology_impression TEXT;
ALTER TABLE dicom_studies ADD COLUMN extracted_measurements JSON;
ALTER TABLE dicom_studies ADD COLUMN clinical_context TEXT;
ALTER TABLE dicom_studies ADD COLUMN clinical_context_processed_at DATETIME;
