# DSAR runbook

## Access / portability

1. Admin authenticates with MFA (if required).
2. `GET /api/admin/dsar/patients/{id}/export` — JSON bundle.
3. Log action: `dsar.export` in audit trail.

## Erasure

1. Confirm legal basis and tenant authorization.
2. `POST /api/admin/dsar/patients/{id}/erase` — cascades DB + files.
3. Checklist:
   - [ ] Patient row and documents
   - [ ] DICOM studies and storage paths
   - [ ] Predictions and jobs
   - [ ] Backups (note: may retain until rotation — document in response)
   - [ ] Chroma/RAG index entries
   - [ ] SIEM copies (customer responsibility)

## Response SLA

Target: 30 calendar days (GDPR Art. 12); expedite for HIPAA where BAA applies.
