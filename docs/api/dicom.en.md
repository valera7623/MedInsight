# API — DICOM

Prefix: `/api/dicom`  
Requires: Bearer token

## POST /api/dicom/upload

Upload a DICOM file (multipart).

| Field | Type | Description |
|-------|------|-------------|
| file | file | `.dcm` |
| patient_id | int | Patient ID |

```bash
curl -X POST http://localhost:8000/api/dicom/upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@scan.dcm" \
  -F "patient_id=1"
```

**Response 201:**

```json
{
  "id": 3,
  "study_uid": "1.2.840.113619.2.55.3...",
  "status": "processing",
  "patient_id": 1
}
```

## GET /api/dicom/studies

List studies.

**Query:** `patient_id`, `modality`, `status`, `search`, `skip`, `limit`

```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/dicom/studies?modality=CT&limit=20"
```

**Response:**

```json
{
  "items": [
    {
      "id": 3,
      "study_uid": "1.2.840...",
      "modality": "CT",
      "study_description": "Chest CT",
      "body_part": "CHEST",
      "status": "ready",
      "frame_count": 120,
      "thumbnail_url": "/api/dicom/studies/3/thumbnail"
    }
  ],
  "total": 5
}
```

## GET /api/dicom/studies/{study_id}

Study details + series.

## GET /api/dicom/studies/{study_id}/viewer

Viewer data (series, frames, window/level).

## GET /api/dicom/studies/{study_id}/thumbnail

PNG preview (first frame).

## GET /api/dicom/frames/{frame_id}/image

PNG for a specific frame.

## DELETE /api/dicom/studies/{study_id}

Delete (admin).

## Statuses

| status | Description |
|--------|-------------|
| processing | Celery processing |
| ready | Ready to view |
| failed | Parse error |

## Errors

| Code | Cause |
|------|-------|
| 413 | DICOM_MAX_FILE_SIZE_MB exceeded |
| 422 | Invalid DICOM |

## Frontend routes

| URL | Description |
|-----|-------------|
| `/dicom` | List |
| `/dicom/viewer/{study_uid}` | Viewer |
