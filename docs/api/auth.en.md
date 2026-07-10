<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Authentication

Auto-generated reference for **Authentication** endpoints (11 operations).

**OpenAPI tags:** auth, preferences

**Endpoints:** 11

---

## GET /api/auth/departments

List Public Departments

**Authentication:** none



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| subdomain | query | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `[{"id": 0, "name": "string"}]` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/auth/departments \
  -H "Authorization: Bearer $JWT"
```

## POST /api/auth/login

Login

**Authentication:** none

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "string",
  "subdomain": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"access_token": "string", "token_type": "bearer", "tenant_id": 0, "role": "string", "demo_mode": false}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/auth/login \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"string","subdomain":"string"}'
```

## GET /api/auth/me

Me

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "email": "string", "full_name": "string", "role": "string", "tenant_id": 0, "department_id": 0, "department...` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/auth/me \
  -H "Authorization: Bearer $JWT"
```

## POST /api/auth/register

Register

**Authentication:** none

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "string",
  "full_name": "string",
  "role": "doctor",
  "subdomain": "string",
  "department_id": 0
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 201 | Successful Response | `{"id": 0, "email": "string", "full_name": "string", "role": "string", "tenant_id": 0, "department_id": 0, "department...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/auth/register \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"string","full_name":"string","role":"doctor","subdomain":"string","department_id":0}'
```

## POST /api/auth/request-reset

Request Reset

**Authentication:** none

**Request Body:**

```json
{
  "email": "user@example.com",
  "subdomain": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 202 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/auth/request-reset \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","subdomain":"string"}'
```

## POST /api/auth/resend-verification

Resend Verification

**Authentication:** none

**Request Body:**

```json
{
  "email": "user@example.com",
  "subdomain": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 202 | Successful Response | `{"detail": "string", "email_verified": true}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/auth/resend-verification \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","subdomain":"string"}'
```

## GET /api/auth/tenants

List Public Tenants

**Authentication:** none




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `[{"id": 0, "name": "string", "subdomain": "string"}]` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/auth/tenants \
  -H "Authorization: Bearer $JWT"
```

## POST /api/auth/verify-email

Verify Email

**Authentication:** none



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| token | query | string | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"detail": "string", "email_verified": true}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/auth/verify-email \
  -H "Authorization: Bearer $JWT"
```

## GET /api/preferences

Read Preferences

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/preferences \
  -H "Authorization: Bearer $JWT"
```

## PUT /api/preferences

Write Preferences

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "theme": "string",
  "settings": {}
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X PUT https://fileguardian.com.ru/api/preferences \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"theme":"string","settings":{}}'
```

## PUT /api/preferences/theme

Write Theme

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "theme": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X PUT https://fileguardian.com.ru/api/preferences/theme \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"theme":"string"}'
```

