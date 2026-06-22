<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# DICOM

Auto-generated reference for **DICOM** endpoints (7 operations).

**OpenAPI tags:** dicom

**Endpoints:** 7

---

## GET /api/dicom/frames/{instance_uid}

Get Dicom Frame

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| instance_uid | path | string | ✅ | — |
| study_uid | query | string | null | ❌ | — |
| frame | query | integer | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/dicom/frames/{instance_uid} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/dicom/studies

List Dicom Studies

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| page | query | integer | ❌ | — |
| limit | query | integer | ❌ | — |
| search | query | string | null | ❌ | — |
| patient_id | query | integer | null | ❌ | — |
| modality | query | string | null | ❌ | — |
| status | query | string | null | ❌ | — |
| date_from | query | string (date-time) | null | ❌ | — |
| date_to | query | string (date-time) | null | ❌ | — |
| sort_by | query | string | ❌ | — |
| sort_order | query | string | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/dicom/studies \
  -H "Authorization: Bearer $JWT"
```

## DELETE /api/dicom/studies/{study_uid}

Delete Dicom Study

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| study_uid | path | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/dicom/studies/{study_uid} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/dicom/studies/{study_uid}

Get Dicom Study

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| study_uid | path | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/dicom/studies/{study_uid} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/dicom/studies/{study_uid}/series/{series_uid}/frames

List Series Frames

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| study_uid | path | string | ✅ | — |
| series_uid | path | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/dicom/studies/{study_uid}/series/{series_uid}/frames \
  -H "Authorization: Bearer $JWT"
```

## GET /api/dicom/studies/{study_uid}/thumbnail

Get Study Thumbnail

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| study_uid | path | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/dicom/studies/{study_uid}/thumbnail \
  -H "Authorization: Bearer $JWT"
```

## POST /api/dicom/upload

Upload Dicom

**Authentication:** `Bearer JWT` (required)


**Form Data:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| patient_id | integer | ✅ | Patient Id |
| file | string | ✅ | File |


**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 202 | Successful Response | `{"study_uid": "string", "study_id": 0, "job_id": "string", "status": "string"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/dicom/upload \
  -H "Authorization: Bearer $JWT" \
  -F "patient_id=value" \
  -F "file=file.pdf"
```

