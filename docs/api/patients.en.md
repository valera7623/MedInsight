# API — Patients

Prefix: `/api/patients`  
Requires: `Authorization: Bearer TOKEN`

## GET /api/patients

List patients (RBAC-aware).

**Query:**

| Parameter | Type | Description |
|-----------|------|-------------|
| skip | int | Offset (default 0) |
| limit | int | Limit (default 20) |
| search | string | Search by name/phone |
| department_id | int | Department filter |

```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/patients?limit=10&search=Ivanov"
```

**Response 200:**

```json
{
  "items": [
    {
      "id": 1,
      "full_name": "Ivan Ivanov",
      "date_of_birth": "1980-05-15",
      "gender": "male",
      "phone": "+79001234567",
      "department_id": 1
    }
  ],
  "total": 42
}
```

## POST /api/patients

Create a patient.

**Body:**

| Field | Type | Required |
|-------|------|----------|
| full_name | string | yes |
| date_of_birth | date | yes |
| gender | string | yes |
| phone | string | yes |
| email | string | no |
| department_id | int | yes |

## GET /api/patients/{id}

Patient record with documents and predictions.

## PUT /api/patients/{id}

Update (WRITE_ROLES).

## DELETE /api/patients/{id}

Delete (admin only).

## GET /api/patients/export/excel

Export list to Excel.

## GET /api/patients/{id}/export/pdf

PDF report for a patient.

## Errors

| Code | Cause |
|------|-------|
| 403 | No access to patient/department |
| 404 | Patient not found |

## Anonymization

For role `researcher`, fields `full_name`, `phone`, `email` are masked in responses.
