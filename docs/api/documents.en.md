# API — Documents

Prefix: `/api/documents`  
Requires: Bearer token

## POST /api/documents/upload

Upload a document (multipart/form-data).

| Field | Type | Description |
|-------|------|-------------|
| file | file | PDF or DOCX |
| patient_id | int | Patient ID |
| document_type | string | discharge, lab, history |

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@discharge.pdf" \
  -F "patient_id=1" \
  -F "document_type=discharge"
```

**Response 201:**

```json
{
  "id": 10,
  "patient_id": 1,
  "filename": "discharge.pdf",
  "status": "uploaded",
  "document_type": "discharge"
}
```

After upload, Celery queues parsing → status `processing` → `parsed`.

## GET /api/documents

List documents.

**Query:** `patient_id`, `status`, `skip`, `limit`

## GET /api/documents/{id}

Document metadata + parsed data (if ready).

**Response (parsed):**

```json
{
  "id": 10,
  "status": "parsed",
  "parsed_data": {
    "diagnoses": ["I10", "E11"],
    "medications": ["metformin", "enalapril"],
    "raw_text_preview": "..."
  }
}
```

## GET /api/documents/{id}/download

Download decrypted file (stream).

## DELETE /api/documents/{id}

Delete (admin / head_of_department).

## Statuses

| status | Description |
|--------|-------------|
| uploaded | Accepted |
| processing | Parsing |
| parsed | Ready |
| failed | Error |

## Errors

| Code | Cause |
|------|-------|
| 403 | No permission for patient |
| 413 | File too large |
| 415 | Unsupported format |
