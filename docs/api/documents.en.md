<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Documents

Auto-generated reference for **Documents** endpoints (7 operations).

**OpenAPI tags:** documents

**Endpoints:** 7

---

## GET /api/documents

List Documents

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| page | query | integer | ❌ | — |
| limit | query | integer | ❌ | — |
| search | query | string | null | ❌ | — |
| patient_id | query | integer | null | ❌ | — |
| document_type | query | string | null | ❌ | — |
| status | query | string | null | ❌ | — |
| sort_by | query | string | ❌ | — |
| sort_order | query | string | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/documents \
  -H "Authorization: Bearer $JWT"
```

## GET /api/documents/patient/{patient_id}

List Patient Documents

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| patient_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `[{"id": 0, "tenant_id": 0, "patient_id": 0, "user_id": 0, "filename": "string", "file_size": 0, "mime_type": "string"...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/documents/patient/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/documents/upload

Upload Document

**Authentication:** `Bearer JWT` (required)


**Form Data:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| patient_id | integer | ✅ | Patient Id |
| document_type | string | ❌ | Document Type |
| file | string | ✅ | File |


**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 201 | Successful Response | `{"id": 0, "tenant_id": 0, "patient_id": 0, "user_id": 0, "filename": "string", "file_size": 0, "mime_type": "string",...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/documents/upload \
  -H "Authorization: Bearer $JWT" \
  -F "patient_id=value" \
  -F "document_type=value" \
  -F "file=file.pdf"
```

## DELETE /api/documents/{document_id}

Delete Document

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| document_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/documents/{document_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/documents/{document_id}

Get Document

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| document_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "tenant_id": 0, "patient_id": 0, "user_id": 0, "filename": "string", "file_size": 0, "mime_type": "string",...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/documents/{document_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/documents/{document_id}/download

Download Document

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| document_id | path | integer | ✅ | — |
| inline | query | boolean | ❌ | Open in browser when supported (PDF) |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/documents/{document_id}/download \
  -H "Authorization: Bearer $JWT"
```

## POST /api/documents/{document_id}/reparse

Reparse Document

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| document_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "tenant_id": 0, "patient_id": 0, "user_id": 0, "filename": "string", "file_size": 0, "mime_type": "string",...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/documents/{document_id}/reparse \
  -H "Authorization: Bearer $JWT"
```

