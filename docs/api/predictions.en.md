<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# Predictions

Auto-generated reference for **Predictions** endpoints (12 operations).

**OpenAPI tags:** predictions

**Endpoints:** 12

---

## GET /api/analytics/dashboard/predictions

Predictions Dashboard

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| department_id | query | integer | null | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"high_risk_patients": [{"id": 0, "name": "string", "readmission_risk": 0.0, "complication_risk": 0.0, "last_predicti...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/dashboard/predictions \
  -H "Authorization: Bearer $JWT"
```

## POST /api/analytics/insights/{patient_id}

Patient Insights

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| patient_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"insights": "string", "recommendations": ["string"]}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/analytics/insights/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/analytics/predict-with-dicom/{patient_id}

Predict With Dicom

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| patient_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"job_id": "string", "status": "string", "prediction_id": 0, "prediction": {}, "dicom_sources": [{}]}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/analytics/predict-with-dicom/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/analytics/predict/status/{job_id}

Prediction Status

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| job_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"status": "string", "result": {}, "error": "string"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/predict/status/{job_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/analytics/predict/{patient_id}

Start Prediction

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| patient_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"job_id": "string", "status": "string"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/analytics/predict/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/analytics/predictions

List Predictions All

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| page | query | integer | ❌ | — |
| limit | query | integer | ❌ | — |
| patient_id | query | integer | null | ❌ | — |
| type | query | string | null | ❌ | — |
| validated | query | boolean | null | ❌ | — |
| sort_by | query | string | ❌ | — |
| sort_order | query | string | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/predictions \
  -H "Authorization: Bearer $JWT"
```

## GET /api/analytics/predictions/detail/{prediction_id}

Get Prediction Detail

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| prediction_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"id": 0, "patient_id": 0, "type": "string", "prediction": {}, "probabilities": {}, "confidence_score": 0.0, "validat...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/predictions/detail/{prediction_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/analytics/predictions/shap/compute/{prediction_id}

Compute Shap Async

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| prediction_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `null` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/analytics/predictions/shap/compute/{prediction_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/analytics/predictions/shap/local/{prediction_id}

Get Prediction Shap

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| prediction_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"target": "readmission", "model_type": "string", "base_value": 0.0, "output_value": 0.0, "contributions": [{"feature...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/predictions/shap/local/{prediction_id} \
  -H "Authorization: Bearer $JWT"
```

## GET /api/analytics/predictions/shap/summary

Get Shap Summary

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| target | query | string | ❌ | Prediction target for global SHAP summary |
| sample_size | query | integer | null | ❌ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"target": "string", "tenant_id": 0, "model_type": "string", "sample_size": 0, "feature_names": ["string"], "summary_...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/predictions/shap/summary \
  -H "Authorization: Bearer $JWT"
```

## GET /api/analytics/predictions/{patient_id}

List Predictions

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| patient_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"predictions": [{"id": 0, "patient_id": 0, "type": "string", "prediction": {}, "probabilities": {}, "confidence_scor...` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X GET https://fileguardian.com.ru/api/analytics/predictions/{patient_id} \
  -H "Authorization: Bearer $JWT"
```

## POST /api/analytics/validate-prediction/{prediction_id}

Validate Prediction

**Authentication:** `Bearer JWT` (required)



**Parameters:**

| Parameter | In | Type | Required | Description |
|-----------|----|------|----------|-------------|
| prediction_id | path | integer | ✅ | — |

**Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 200 | Successful Response | `{"status": "string"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["string"], "msg": "string", "type": "string"}]}` |

**Example:**

```bash
curl -X POST https://fileguardian.com.ru/api/analytics/validate-prediction/{prediction_id} \
  -H "Authorization: Bearer $JWT"
```

