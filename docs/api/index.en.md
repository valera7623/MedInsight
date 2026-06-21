# API — Overview

MedInsight provides a REST API on FastAPI.

## Base URL

```
https://medinsight.fileguardian.info/api
```

Locally: `http://localhost:8000/api`

## Interactive documentation

| URL | Format |
|-----|--------|
| `/docs` | Swagger UI (OpenAPI 3) |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI JSON |

OpenAPI is **generated automatically** from FastAPI code.

## Authentication

JWT Bearer token:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://example.com/api/patients
```

Obtain a token: [auth.md](auth.md)

## Response format

Success — JSON with data.

Errors:

```json
{
  "detail": "Error message"
}
```

| Code | Meaning |
|------|---------|
| 400 | Bad request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not found |
| 402 | Plan limit |
| 422 | Validation error |
| 500 | Server error |

## Pagination

Lists support `skip` and `limit`:

```
GET /api/patients?skip=0&limit=20
```

## Multi-tenancy

Registration/login uses the clinic `subdomain`. JWT contains `tenant_id` — all data is isolated.

## API sections

| Document | Prefix |
|----------|--------|
| [Authentication](auth.md) | `/api/auth` |
| [Patients](patients.md) | `/api/patients` |
| [Documents](documents.md) | `/api/documents` |
| [DICOM](dicom.md) | `/api/dicom` |
| [Analytics](analytics.md) | `/api/analytics`, `/api/dashboard` |
| [Predictions](predictions.md) | `/api/predictions` |

## WebSocket

```
ws://host/ws/notifications?token=JWT
```

Events: `document_parsed`, `prediction_ready`, `dicom_processed`.

## Rate limiting

nginx rate limit recommended on production. In the app — plan limits on predictions.

## Versioning

Current API version is not in the URL. Breaking changes are documented in [Changelog](../misc/changelog.md).
