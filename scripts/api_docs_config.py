"""Configuration for OpenAPI → Markdown documentation generation."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# MkDocs suffix i18n: English generated files live alongside Russian manuals.
# Logical layout: docs/en/api/*.md → physical: docs/api/*.en.md
OUTPUT_DIR = PROJECT_ROOT / "docs" / "api"
OUTPUT_LOCALE_SUFFIX = ".en"  # produces index.en.md, auth.en.md, …
MKDOCS_PATH = PROJECT_ROOT / "mkdocs.yml"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

TAG_GROUPS: dict[str, dict[str, object]] = {
    "auth": {"title": "Authentication", "order": 1, "openapi_tags": ["auth", "preferences"]},
    "patients": {"title": "Patients", "order": 2, "openapi_tags": ["patients"]},
    "documents": {"title": "Documents", "order": 3, "openapi_tags": ["documents"]},
    "dicom": {"title": "DICOM", "order": 4, "openapi_tags": ["dicom"]},
    "analytics": {"title": "Analytics", "order": 5, "openapi_tags": ["analytics"]},
    "predictions": {"title": "Predictions", "order": 6, "openapi_tags": ["predictions"]},
    "exports": {"title": "Export", "order": 7, "openapi_tags": ["export"]},
    "webhooks": {"title": "Webhooks", "order": 8, "openapi_tags": ["webhooks", "payment-webhooks"]},
    "payments": {"title": "Payments", "order": 9, "openapi_tags": ["payments"]},
    "admin": {
        "title": "Admin",
        "order": 10,
        "openapi_tags": ["admin", "admin-backup", "users", "telegram"],
    },
    "websocket": {"title": "WebSocket", "order": 11, "openapi_tags": ["websocket"], "static_template": "api_websocket_static.j2"},
}

# OpenAPI tag → output file slug (first match wins via reverse lookup in generator)
TAG_TO_GROUP: dict[str, str] = {}
for slug, meta in TAG_GROUPS.items():
    for tag in meta.get("openapi_tags", [slug]):  # type: ignore[union-attr]
        TAG_TO_GROUP[str(tag)] = slug

EXCLUDED_TAGS = frozenset({"internal", "debug", "health"})

CURL_EXAMPLE_ENABLED = True
CURL_EXAMPLE_HOST = "https://fileguardian.com.ru"

DEFAULT_OPENAPI_URL = "http://localhost:8000/openapi.json"
OPENAPI_CACHE_FILE = PROJECT_ROOT / "openapi.json"

GENERATED_BANNER = (
    "<!-- AUTO-GENERATED from OpenAPI — do not edit manually. "
    "Run: python scripts/generate_api_docs.py --import-app --update-nav -->\n\n"
)

MKDOCS_NAV_START = "# api-docs-generated-start"
MKDOCS_NAV_END = "# api-docs-generated-end"

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

SCHEMA_TYPE_EXAMPLES: dict[str, object] = {
    "string": "string",
    "integer": 0,
    "number": 0.0,
    "boolean": True,
    "object": {},
    "array": [],
    "null": None,
}

AUTH_LABELS: dict[str, str] = {
    "HTTPBearer": "Bearer JWT",
    "OAuth2PasswordBearer": "OAuth2 Bearer",
    "APIKeyHeader": "API Key",
}
