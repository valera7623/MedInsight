<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Export

Auto-generated reference for **Export** endpoints (7 operations).

**OpenAPI tags:** export

**Endpoints:** 7

---

## POST /api/export/audit

Export Audit

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "filters": {},
  "columns": [
    "string"
  ]
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/export/audit \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"filters":{},"columns":["string"]}'
```

## POST /api/export/documents

Export Documents

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "filters": {},
  "columns": [
    "string"
  ]
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/export/documents \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"filters":{},"columns":["string"]}'
```

## GET /api/export/download/{job_id}

Download Export

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| job_id | path | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/export/download/{job_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/export/patient/{patient_id}

Export Patient Pdf

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| patient_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/export/patient/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/export/patients

Export Patients

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "filters": {},
  "columns": [
    "string"
  ]
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/export/patients \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"filters":{},"columns":["string"]}'
```

## POST /api/export/predictions

Export Predictions

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "filters": {},
  "columns": [
    "string"
  ]
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/export/predictions \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"filters":{},"columns":["string"]}'
```

## POST /api/export/users

Export Users

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "filters": {},
  "columns": [
    "string"
  ]
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/export/users \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"filters":{},"columns":["string"]}'
```

