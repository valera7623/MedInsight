<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Webhooks

Auto-generated reference for **Webhooks** endpoints (7 operations).

**OpenAPI tags:** webhooks, payment-webhooks

**Endpoints:** 7

---

## GET /api/webhooks

List Webhooks

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `[{"id": 0, "tenant_id": 0, "url": "string", "events": ["string"], "is_active": true, "created_at": "2026-06-21T12:00:...` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/webhooks \
  -H "Authorization: Bearer $JWT"
```

## POST /api/webhooks/register

Register Webhook

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "url": "string",
  "events": [
    "string"
  ],
  "secret": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 201 | Successful Response | `{"id": 0, "tenant_id": 0, "url": "string", "events": ["string"], "is_active": true, "created_at": "2026-06-21T12:00:0...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/webhooks/register \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"url":"string","events":["string"],"secret":"string"}'
```

## DELETE /api/webhooks/{webhook_id}

Delete Webhook

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| webhook_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 204 | Successful Response | `{}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X DELETE https://fileguardian.com.ru/api/webhooks/{webhook_id} \
  -H "Authorization: Bearer $JWT"
```

## PUT /api/webhooks/{webhook_id}

Update Webhook

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "url": "string",
  "events": [
    "string"
  ],
  "is_active": true,
  "secret": "string"
}
```


**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| webhook_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "tenant_id": 0, "url": "string", "events": ["string"], "is_active": true, "created_at": "2026-06-21T12:00:0...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X PUT https://fileguardian.com.ru/api/webhooks/{webhook_id} \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"url":"string","events":["string"],"is_active":true,"secret":"string"}'
```

## POST /api/webhooks/{webhook_id}/test

Test Webhook

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| webhook_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/webhooks/{webhook_id}/test \
  -H "Authorization: Bearer $JWT"
```

## POST /webhooks/stripe

Stripe Webhook

**Authentication:** none



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| Stripe-Signature | header | string | null | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/webhooks/stripe \
  -H "Authorization: Bearer $JWT"
```

## POST /webhooks/yookassa

Yookassa Webhook

**Authentication:** none




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/webhooks/yookassa \
  -H "Authorization: Bearer $JWT"
```

