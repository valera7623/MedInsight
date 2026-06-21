# API — Analytics

Prefixes: `/api/analytics`, `/api/dashboard`  
Requires: Bearer token

## GET /api/dashboard/stats

Summary statistics for the dashboard.

**Query:** `department_id` (optional)

```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/dashboard/stats?department_id=1"
```

**Response 200:**

```json
{
  "patients_count": 150,
  "documents_count": 320,
  "diagnoses_count": 45,
  "top_diagnoses": [
    {"code": "I10", "count": 42},
    {"code": "E11", "count": 38}
  ],
  "top_medications": [
    {"name": "metformin", "count": 55}
  ],
  "dicom_studies_count": 12,
  "dicom_by_modality": {"CT": 8, "MR": 4}
}
```

## GET /api/analytics/diagnoses

Top diagnoses with pagination.

## GET /api/analytics/medications

Top medications.

## GET /api/analytics/departments

Statistics by department.

## GET /api/analytics/risk-summary

Risk summary (high/medium/low counts).

## GET /api/analytics/recent-patients

Recently added patients.

## GET /api/analytics/export/excel

Export analytics to Excel.

## Webhooks (admin)

### GET /api/webhooks

List clinic webhooks.

### POST /api/webhooks

Create webhook (URL + events).

### DELETE /api/webhooks/{id}

Delete.

## RBAC

- `viewer`, `researcher` — read-only statistics;
- `researcher` — aggregates without PII in detailed lists;
- export — per role policy.

## Errors

| Code | Cause |
|------|-------|
| 403 | No access to department |
