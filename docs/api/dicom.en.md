<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# DICOM

Auto-generated reference for **DICOM** endpoints (11 operations).

**OpenAPI tags:** dicom

**Endpoints:** 11

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

## GET /api/dicom/studies/{study_uid}/archive

Download Dicom Archive

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
curl -X GET https://fileguardian.com.ru/api/dicom/studies/{study_uid}/archive \
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

## POST /api/dicom/upload-zip

Upload Dicom Zip

**Authentication:** `Bearer JWT` (required)


**Form Data:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| patient_id | integer | ✅ | Patient Id |
| zip_file | string | ✅ | Zip File |


**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 202 | Successful Response | `{"study_uid": "string", "study_id": 0, "job_id": "string", "status": "string", "total_files": 0}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/dicom/upload-zip \
  -H "Authorization: Bearer $JWT" \
  -F "patient_id=value" \
  -F "zip_file=file.pdf"
```

## GET /api/dicom/upload-zip/status/{job_id}

Get Dicom Zip Status

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| job_id | path | string | ✅ | — |
| study_id | query | integer | null | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"job_id": "string", "status": "string", "study_uid": "string", "processed_files": 0, "total_files": 0, "percent": 0,...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/dicom/upload-zip/status/{job_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/dicom/upload/status/{study_id}

Get Dicom Upload Status

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| study_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"study_id": 0, "study_uid": "string", "status": "string", "num_instances": 0, "error_message": "string"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/dicom/upload/status/{study_id} \
  -H "Authorization: Bearer $JWT"
```

