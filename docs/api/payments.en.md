<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Payments

Auto-generated reference for **Payments** endpoints (6 operations).

**OpenAPI tags:** payments

**Endpoints:** 6

---

## POST /api/payments/cancel-subscription

Cancel Subscription

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/payments/cancel-subscription \
  -H "Authorization: Bearer $JWT"
```

## POST /api/payments/create-checkout

Create Checkout

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "plan_type": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/payments/create-checkout \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"plan_type":"string"}'
```

## GET /api/payments/history

Payment History

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/payments/history \
  -H "Authorization: Bearer $JWT"
```

## GET /api/payments/prices

List Prices

**Authentication:** none




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/payments/prices \
  -H "Authorization: Bearer $JWT"
```

## GET /api/payments/subscription

Get Subscription

**Authentication:** `Bearer JWT` (required)




**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"plan_type": "string", "status": "string", "reports_limit": 0, "reports_used": 0, "reports_remaining": 0, "current_p...` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/payments/subscription \
  -H "Authorization: Bearer $JWT"
```

## POST /api/payments/yookassa/create

Create Yookassa

**Authentication:** `Bearer JWT` (required)

**Request Body:**

```json
{
  "plan_type": "string"
}
```



**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/payments/yookassa/create \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"plan_type":"string"}'
```

