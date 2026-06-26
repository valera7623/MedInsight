<!-- AUTO-GENERATED from OpenAPI — do not edit manually. Run: python scripts/generate_api_docs.py --import-app --update-nav -->

# API Reference

Machine-readable API reference generated from the FastAPI OpenAPI schema. For interactive exploration use Swagger UI at `/docs`.

## Base URL

```
https://fileguardian.com.ru/api
```

## Interactive documentation

| URL | Format |
|-----|--------|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI 3 JSON schema |

## Authentication

Most endpoints require a JWT Bearer token:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" https://fileguardian.com.ru/api/auth/me
```

Obtain a token via `POST /api/auth/login`.

## Sections

| Section | Description |
|---------|-------------|
| [Authentication](auth.md) | 11 endpoint(s) |
| [Patients](patients.md) | 5 endpoint(s) |
| [Documents](documents.md) | 7 endpoint(s) |
| [DICOM](dicom.md) | 11 endpoint(s) |
| [Analytics](analytics.md) | 1 endpoint(s) |
| [Predictions](predictions.md) | 12 endpoint(s) |
| [Export](exports.md) | 10 endpoint(s) |
| [Webhooks](webhooks.md) | 7 endpoint(s) |
| [Payments](payments.md) | 6 endpoint(s) |
| [Admin](admin.md) | 38 endpoint(s) |

## Error format

```json
{
  "detail": "Human-readable error message"
}
```

## Common status codes

| Code | Meaning |
|------|---------|
| 400 | Bad request / validation error |
| 401 | Not authenticated |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 402 | Plan limit exceeded (predictions) |
| 422 | Validation error (Pydantic) |
| 500 | Internal server error |

---

*Generated from OpenAPI 3.1.0 — 2026-06-26 23:38 UTC*