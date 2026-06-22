<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Analytics

Auto-generated reference for **Analytics** endpoints (1 operations).

**OpenAPI tags:** analytics

**Endpoints:** 1

---

## GET /api/analytics/dashboard

Dashboard

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| department_id | query | integer | null | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"total_patients": 0, "total_documents": 0, "total_dicom_studies": 0, "dicom_modalities": {}, "dicom_body_parts": {},...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/dashboard \
  -H "Authorization: Bearer $JWT"
```

