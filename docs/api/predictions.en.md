# API — Predictions

Prefix: `/api/predictions`  
Requires: Bearer token, WRITE_ROLES for creation

## POST /api/predictions/run

Run a prediction for a patient.

**Body:**

```json
{
  "patient_id": 1
}
```

```bash
curl -X POST http://localhost:8000/api/predictions/run \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"patient_id": 1}'
```

**Response 202:**

```json
{
  "task_id": "abc-123",
  "status": "processing",
  "message": "Prediction queued"
}
```

## GET /api/predictions/patient/{patient_id}

Patient prediction history.

**Response:**

```json
{
  "items": [
    {
      "id": 7,
      "patient_id": 1,
      "readmission_risk": 0.35,
      "complication_risk": 0.22,
      "risk_level": "medium",
      "gpt_explanation": "Patient with comorbidities...",
      "created_at": "2026-06-20T14:30:00Z",
      "validated": null
    }
  ]
}
```

## GET /api/predictions/high-risk

High-risk patients (dashboard).

**Query:** `department_id`, `limit`

## POST /api/predictions/{id}/validate

Clinician validation of a prediction.

**Body:**

```json
{
  "is_accurate": true,
  "comment": "Agree with the assessment"
}
```

## GET /api/predictions/export/excel

Export predictions to Excel.

## Plan limits

When monthly limit is exceeded:

**Response 402:**

```json
{
  "detail": "Monthly analysis limit exceeded",
  "limit": 5,
  "used": 5
}
```

## Asynchronous processing

Result is available after Celery task completes. Subscribe to WebSocket or poll `GET /api/predictions/patient/{id}`.

## Fallback

If GPT is unavailable, `gpt_explanation` may be `null`; risks are calculated rule-based.
