<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Patients

Auto-generated reference for **Patients** endpoints (5 operations).

**OpenAPI tags:** patients

**Endpoints:** 5

---

## GET /api/patients

List Patients

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| page | query | integer | ❌ | — |
| limit | query | integer | ❌ | — |
| page_size | query | integer | null | ❌ | Алиас limit (совместимость) |
| search | query | string | null | ❌ | — |
| department_id | query | integer | null | ❌ | — |
| attending_doctor_id | query | integer | null | ❌ | — |
| sort_by | query | string | ❌ | — |
| sort_order | query | string | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/patients \
  -H "Authorization: Bearer $JWT"
```

## POST /api/patients

Create Patient

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "middle_name": null,
  "birth_date": "1980-05-15",
  "gender": "M",
  "phone": "+1234567890",
  "email": "user@example.com",
  "department_id": 0,
  "attending_doctor_id": 0
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 201 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/patients \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"John","last_name":"Doe","middle_name":null,"birth_date":"1980-05-15","gender":"M","phone":"+1234567890","email":"user@example.com","department_id":0,"attending_doctor_id":0}'
```

## DELETE /api/patients/{patient_id}

Delete Patient

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| patient_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/patients/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/patients/{patient_id}

Get Patient

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
curl -X GET https://fileguardian.com.ru/api/patients/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## PUT /api/patients/{patient_id}

Update Patient

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "middle_name": null,
  "birth_date": "1980-05-15",
  "gender": "M",
  "phone": "string",
  "email": "user@example.com",
  "department_id": 0,
  "attending_doctor_id": 0
}
```


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
curl -X PUT https://fileguardian.com.ru/api/patients/{patient_id} \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"John","last_name":"Doe","middle_name":null,"birth_date":"1980-05-15","gender":"M","phone":"string","email":"user@example.com","department_id":0,"attending_doctor_id":0}'
```

