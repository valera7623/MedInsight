<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Admin

Auto-generated reference for **Admin** endpoints (39 operations).

**OpenAPI tags:** admin, admin-backup, users, telegram

**Endpoints:** 39

---

## GET /api/admin/audit

List Audit

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| tenant_id | query | integer | null | ❌ | — |
| action | query | string | null | ❌ | — |
| user_id | query | integer | null | ❌ | — |
| from_date | query | string | null | ❌ | — |
| to_date | query | string | null | ❌ | — |
| page | query | integer | null | ❌ | — |
| limit | query | integer | ❌ | — |
| sort_by | query | string | ❌ | — |
| sort_order | query | string | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/audit \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/backup/create

Create Backup

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "type": "full"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/backup/create \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"type":"full"}'
```

## GET /api/admin/backup/download/{backup_id}

Download Backup

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| backup_id | path | string | ✅ | — |
| type | query | string | null | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/backup/download/{backup_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/admin/backup/list

List Backups

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/backup/list \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/backup/restore

Restore Backup

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "backup_id": "string",
  "type": "full",
  "confirm": false
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/backup/restore \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"backup_id":"string","type":"full","confirm":false}'
```

## GET /api/admin/backup/status/{job_id}

Backup Status

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
curl -X GET https://fileguardian.com.ru/api/admin/backup/status/{job_id} \
  -H "Authorization: Bearer $JWT"
```

## DELETE /api/admin/backup/{backup_id}

Delete Backup

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| backup_id | path | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/admin/backup/{backup_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/cache/cleanup

Cache Cleanup

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/cache/cleanup \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/cache/invalidate

Cache Invalidate

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "patient_id": 0,
  "all": false
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/cache/invalidate \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"patient_id":0,"all":false}'
```

## GET /api/admin/cache/stats

Cache Stats

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/cache/stats \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/cache/warmup

Cache Warmup

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "patient_ids": [
    0
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
curl -X POST https://fileguardian.com.ru/api/admin/cache/warmup \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"patient_ids":[0]}'
```

## GET /api/admin/departments

List Departments

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| tenant_id | query | integer | null | ❌ | — |
| page | query | integer | null | ❌ | — |
| limit | query | integer | ❌ | — |
| search | query | string | null | ❌ | — |
| sort_by | query | string | ❌ | — |
| sort_order | query | string | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/departments \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/departments

Create Department

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "name": "string",
  "head_doctor_id": 0,
  "tenant_id": 0
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 201 | Successful Response | `{"id": 0, "tenant_id": 0, "name": "string", "head_doctor_id": 0, "created_at": "2026-06-21T12:00:00Z"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/departments \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"string","head_doctor_id":0,"tenant_id":0}'
```

## DELETE /api/admin/departments/{dept_id}

Delete Department

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| dept_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/admin/departments/{dept_id} \
  -H "Authorization: Bearer $JWT"
```

## PUT /api/admin/departments/{dept_id}

Update Department

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "name": "string",
  "head_doctor_id": 0
}
```


**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| dept_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "tenant_id": 0, "name": "string", "head_doctor_id": 0, "created_at": "2026-06-21T12:00:00Z"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X PUT https://fileguardian.com.ru/api/admin/departments/{dept_id} \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"string","head_doctor_id":0}'
```

## POST /api/admin/encryption/rotate

Rotate Key

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "new_key": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/encryption/rotate \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"new_key":"string"}'
```

## GET /api/admin/health

Admin Health

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"status": "string", "tenant_mode": true, "encryption_enabled": true, "tenants_count": 0, "users_count": 0, "patients...` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/health \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/self-healing/confirm/{fix_id}

Self Healing Confirm

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| fix_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/self-healing/confirm/{fix_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/admin/self-healing/fixes

Self Healing List

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/self-healing/fixes \
  -H "Authorization: Bearer $JWT"
```

## DELETE /api/admin/self-healing/fixes/{fix_id}

Self Healing Delete

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| fix_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/admin/self-healing/fixes/{fix_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/self-healing/seed-fixes

Self Healing Seed

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| overwrite | query | boolean | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/self-healing/seed-fixes \
  -H "Authorization: Bearer $JWT"
```

## GET /api/admin/self-healing/stats

Self Healing Stats

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/self-healing/stats \
  -H "Authorization: Bearer $JWT"
```

## GET /api/admin/tenants

List Tenants

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `[{"id": 0, "name": "string", "subdomain": "string", "settings": {}, "is_active": true, "created_at": "2026-06-21T12:0...` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/tenants \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/tenants

Create Tenant

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "name": "string",
  "subdomain": "string",
  "settings": {}
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 201 | Successful Response | `{"id": 0, "name": "string", "subdomain": "string", "settings": {}, "is_active": true, "created_at": "2026-06-21T12:00...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/tenants \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"string","subdomain":"string","settings":{}}'
```

## DELETE /api/admin/tenants/{tenant_id}

Delete Tenant

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| tenant_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/admin/tenants/{tenant_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/admin/tenants/{tenant_id}

Get Tenant

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| tenant_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "name": "string", "subdomain": "string", "settings": {}, "is_active": true, "created_at": "2026-06-21T12:00...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/tenants/{tenant_id} \
  -H "Authorization: Bearer $JWT"
```

## PUT /api/admin/tenants/{tenant_id}

Update Tenant

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "name": "string",
  "settings": {},
  "is_active": true
}
```


**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| tenant_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "name": "string", "subdomain": "string", "settings": {}, "is_active": true, "created_at": "2026-06-21T12:00...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X PUT https://fileguardian.com.ru/api/admin/tenants/{tenant_id} \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"string","settings":{},"is_active":true}'
```

## GET /api/admin/users

List Users

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| tenant_id | query | integer | null | ❌ | — |
| page | query | integer | null | ❌ | — |
| limit | query | integer | ❌ | — |
| search | query | string | null | ❌ | — |
| role | query | string | null | ❌ | — |
| is_active | query | boolean | null | ❌ | — |
| sort_by | query | string | ❌ | — |
| sort_order | query | string | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/admin/users \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/users

Create User

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "string",
  "full_name": "string",
  "role": "doctor",
  "tenant_id": 0,
  "department_id": 0,
  "can_see_all_patients": false
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 201 | Successful Response | `{"id": 0, "email": "string", "full_name": "string", "role": "string", "tenant_id": 0, "department_id": 0, "can_see_al...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/users \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"string","full_name":"string","role":"doctor","tenant_id":0,"department_id":0,"can_see_all_patients":false}'
```

## DELETE /api/admin/users/{user_id}

Delete User

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| user_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/admin/users/{user_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/admin/users/{user_id}/block

Block User

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| user_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "email": "string", "full_name": "string", "role": "string", "tenant_id": 0, "department_id": 0, "can_see_al...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/users/{user_id}/block \
  -H "Authorization: Bearer $JWT"
```

## PUT /api/admin/users/{user_id}/password

Reset User Password

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "password": "string"
}
```


**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| user_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X PUT https://fileguardian.com.ru/api/admin/users/{user_id}/password \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"password":"string"}'
```

## PUT /api/admin/users/{user_id}/role

Update User Role

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "role": "string"
}
```


**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| user_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "email": "string", "full_name": "string", "role": "string", "tenant_id": 0, "department_id": 0, "can_see_al...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X PUT https://fileguardian.com.ru/api/admin/users/{user_id}/role \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"role":"string"}'
```

## POST /api/admin/users/{user_id}/unblock

Unblock User

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| user_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "email": "string", "full_name": "string", "role": "string", "tenant_id": 0, "department_id": 0, "can_see_al...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/admin/users/{user_id}/unblock \
  -H "Authorization: Bearer $JWT"
```

## DELETE /api/telegram/link

Unlink Telegram Account

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/telegram/link \
  -H "Authorization: Bearer $JWT"
```

## POST /api/telegram/link

Link Telegram Account

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "code": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/telegram/link \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"code":"string"}'
```

## GET /api/telegram/status

Telegram Status

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/telegram/status \
  -H "Authorization: Bearer $JWT"
```

## POST /api/telegram/subscribe

Update Telegram Subscriptions

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "events": [
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
curl -X POST https://fileguardian.com.ru/api/telegram/subscribe \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"events":["string"]}'
```

## GET /api/users/me

Get Profile

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "email": "string", "full_name": "string", "role": "string", "tenant_id": 0, "department_id": 0, "department...` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/users/me \
  -H "Authorization: Bearer $JWT"
```

