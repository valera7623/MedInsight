-- Phase: AI medical document parser fields on documents
ALTER TABLE documents ADD COLUMN IF NOT EXISTS parsed_by_ai BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS parse_confidence DOUBLE PRECISION;
