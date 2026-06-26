<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Export

Auto-generated reference for **Export** endpoints (10 operations).

**OpenAPI tags:** export

**Endpoints:** 10

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

## POST /api/export/patient-card

Export Patient Card Docx

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "patient_id": 0,
  "format": "docx",
  "sections": [
    "string"
  ],
  "async_export": false,
  "watermark": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/export/patient-card \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"patient_id":0,"format":"docx","sections":["string"],"async_export":false,"watermark":"string"}'
```

## GET /api/export/patient-card/download/{job_id}

Download Async Patient Card

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
curl -X GET https://fileguardian.com.ru/api/export/patient-card/download/{job_id} \
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

## GET /api/export/status/{job_id}

Export Status

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| job_id | path | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"job_id": "string", "state": "string", "ready": true, "status": "string", "cache_hit": false, "cache_source": "strin...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/export/status/{job_id} \
  -H "Authorization: Bearer $JWT"
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

