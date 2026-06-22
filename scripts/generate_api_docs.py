#!/usr/bin/env python3
"""Generate Markdown API documentation from FastAPI OpenAPI schema."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from api_docs_config import (
    AUTH_LABELS,
    CURL_EXAMPLE_ENABLED,
    CURL_EXAMPLE_HOST,
    DEFAULT_OPENAPI_URL,
    EXCLUDED_TAGS,
    GENERATED_BANNER,
    HTTP_METHODS,
    MKDOCS_PATH,
    OPENAPI_CACHE_FILE,
    OUTPUT_DIR,
    OUTPUT_LOCALE_SUFFIX,
    PROJECT_ROOT,
    SCHEMA_TYPE_EXAMPLES,
    TAG_GROUPS,
    TAG_TO_GROUP,
    TEMPLATES_DIR,
)

# Allow running as `python scripts/generate_api_docs.py`
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


@dataclass
class ParamRow:
    name: str
    location: str
    type: str
    required: str
    description: str


@dataclass
class ResponseRow:
    status: str
    description: str
    example: str


@dataclass
class EndpointDoc:
    method: str
    path: str
    description: str
    auth_label: str | None
    parameters: list[ParamRow] = field(default_factory=list)
    request_body_json: str | None = None
    request_form_fields: list[ParamRow] | None = None
    responses: list[ResponseRow] = field(default_factory=list)
    curl_example: str | None = None
    order: tuple[int, str, str] = (0, "", "")


class SchemaResolver:
    """Resolve JSON Schema $ref pointers within OpenAPI components."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.components = schema.get("components", {})
        self._resolve_cache: dict[str, dict[str, Any]] = {}

    def resolve(self, node: Any, depth: int = 0) -> Any:
        if depth > 32:
            return node
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if ref in self._resolve_cache:
                    return self._resolve_cache[ref]
                resolved = self._resolve_ref(ref)
                self._resolve_cache[ref] = resolved
                merged = {**resolved, **{k: v for k, v in node.items() if k != "$ref"}}
                return self.resolve(merged, depth + 1)
            return {k: self.resolve(v, depth + 1) for k, v in node.items()}
        if isinstance(node, list):
            return [self.resolve(item, depth + 1) for item in node]
        return node

    def _resolve_ref(self, ref: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            return {"type": "object", "description": ref}
        parts = ref.lstrip("#/").split("/")
        node: Any = self.schema
        for part in parts:
            if not isinstance(node, dict):
                return {"type": "object"}
            node = node.get(part, {})
        if not isinstance(node, dict):
            return {"type": "object"}
        return node


class OpenAPIDocGenerator:
    def __init__(self, openapi: dict[str, Any]) -> None:
        self.openapi = openapi
        self.resolver = SchemaResolver(openapi)
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(default=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, tag_filter: set[str] | None = None, output_dir: Path | None = None) -> dict[str, Path]:
        grouped = self._group_operations(tag_filter)
        out = output_dir or OUTPUT_DIR
        out.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}

        for slug in sorted(TAG_GROUPS, key=lambda s: int(TAG_GROUPS[s]["order"])):  # type: ignore[arg-type]
            if tag_filter and slug not in tag_filter:
                continue
            endpoints = grouped.get(slug, [])
            static_template = TAG_GROUPS[slug].get("static_template")
            if not endpoints and static_template:
                content = self.env.get_template(str(static_template)).render(
                    banner=GENERATED_BANNER,
                    host=CURL_EXAMPLE_HOST.replace("https://", "").replace("http://", ""),
                )
                filename = f"{slug}{OUTPUT_LOCALE_SUFFIX}.md"
                path = out / filename
                path.write_text(content, encoding="utf-8")
                written[slug] = path
                grouped[slug] = []  # for index count
                continue
            if not endpoints:
                continue
            endpoints.sort(key=lambda e: (e.path, e.method))
            meta = TAG_GROUPS[slug]
            content = self.env.get_template("api_tag.j2").render(
                banner=GENERATED_BANNER,
                title=str(meta["title"]),
                description=self._group_description(slug, endpoints),
                openapi_tags=meta.get("openapi_tags", [slug]),
                endpoints=endpoints,
            )
            filename = f"{slug}{OUTPUT_LOCALE_SUFFIX}.md"
            path = out / filename
            path.write_text(content, encoding="utf-8")
            written[slug] = path

        index_path = self._write_index(grouped, out)
        written["index"] = index_path
        return written

    def _group_description(self, slug: str, endpoints: list[EndpointDoc]) -> str:
        title = str(TAG_GROUPS[slug]["title"])
        return f"Auto-generated reference for **{title}** endpoints ({len(endpoints)} operations)."

    def _write_index(self, grouped: dict[str, list[EndpointDoc]], output_dir: Path) -> Path:
        sections = []
        for slug in sorted(TAG_GROUPS, key=lambda s: int(TAG_GROUPS[s]["order"])):  # type: ignore[arg-type]
            endpoints = grouped.get(slug, [])
            if not endpoints:
                continue
            count = len(endpoints)
            if not count and TAG_GROUPS[slug].get("static_template"):
                count = 1
            sections.append(
                {
                    "title": str(TAG_GROUPS[slug]["title"]),
                    "filename": f"{slug}.md",
                    "endpoint_count": count,
                }
            )
        content = self.env.get_template("api_index.j2").render(
            banner=GENERATED_BANNER,
            description=(
                "Machine-readable API reference generated from the FastAPI OpenAPI schema. "
                "For interactive exploration use Swagger UI at `/docs`."
            ),
            base_url=CURL_EXAMPLE_HOST.rstrip("/"),
            sections=sections,
            openapi_version=self.openapi.get("openapi", "3.x"),
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )
        path = output_dir / f"index{OUTPUT_LOCALE_SUFFIX}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _group_operations(self, tag_filter: set[str] | None) -> dict[str, list[EndpointDoc]]:
        grouped: dict[str, list[EndpointDoc]] = defaultdict(list)
        paths = self.openapi.get("paths", {})

        for path, path_item in sorted(paths.items()):
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                if operation.get("x-hide-docs") is True:
                    continue

                op_tags = operation.get("tags") or ["default"]
                primary_tag = op_tags[0]
                if primary_tag in EXCLUDED_TAGS:
                    continue

                group_slug = TAG_TO_GROUP.get(primary_tag)
                if not group_slug:
                    continue
                if tag_filter and group_slug not in tag_filter:
                    continue

                endpoint = self._build_endpoint(method.upper(), path, operation)
                grouped[group_slug].append(endpoint)

        return grouped

    def _build_endpoint(self, method: str, path: str, operation: dict[str, Any]) -> EndpointDoc:
        x_docs = operation.get("x-docs") or {}
        description = (
            x_docs.get("description")
            or operation.get("summary")
            or operation.get("description")
            or f"{method} {path}"
        )
        description = str(description).strip()

        auth_label = self._auth_label(operation.get("security") or self.openapi.get("security"))

        parameters = self._parameters(operation.get("parameters") or [])
        request_body_json = None
        request_form_fields = None

        request_body = operation.get("requestBody")
        if request_body:
            content = request_body.get("content") or {}
            if "application/json" in content:
                schema = self.resolver.resolve(content["application/json"].get("schema", {}))
                example = self._example_from_schema(schema)
                request_body_json = json.dumps(example, indent=2, ensure_ascii=False)
            elif "multipart/form-data" in content:
                schema = self.resolver.resolve(content["multipart/form-data"].get("schema", {}))
                request_form_fields = self._schema_fields(schema, request_body.get("required") or [])

        responses = self._responses(operation.get("responses") or {})
        curl_example = None
        if CURL_EXAMPLE_ENABLED:
            curl_example = self._curl_example(method, path, request_body_json, request_form_fields)

        return EndpointDoc(
            method=method,
            path=path,
            description=description,
            auth_label=auth_label,
            parameters=parameters,
            request_body_json=request_body_json,
            request_form_fields=request_form_fields,
            responses=responses,
            curl_example=curl_example,
        )

    def _auth_label(self, security: list[Any] | None) -> str | None:
        if not security:
            return None
        for requirement in security:
            if not isinstance(requirement, dict):
                continue
            for scheme_name in requirement:
                schemes = self.openapi.get("components", {}).get("securitySchemes", {})
                scheme = schemes.get(scheme_name, {})
                scheme_type = scheme.get("type", "")
                if scheme_type == "http" and scheme.get("scheme") == "bearer":
                    return AUTH_LABELS.get("HTTPBearer", "Bearer JWT")
                if scheme_type == "apiKey":
                    return AUTH_LABELS.get("APIKeyHeader", "API Key")
                if scheme_type == "oauth2":
                    return AUTH_LABELS.get("OAuth2PasswordBearer", "OAuth2 Bearer")
                return scheme_name
        return "Bearer JWT"

    def _parameters(self, params: list[Any]) -> list[ParamRow]:
        rows: list[ParamRow] = []
        for raw in params:
            if not isinstance(raw, dict):
                continue
            resolved = self.resolver.resolve(raw)
            schema = resolved.get("schema", {"type": "string"})
            rows.append(
                ParamRow(
                    name=str(resolved.get("name", "")),
                    location=str(resolved.get("in", "query")),
                    type=self._schema_type_label(schema),
                    required="✅" if resolved.get("required") else "❌",
                    description=str(resolved.get("description") or "—"),
                )
            )
        return rows

    def _as_required_set(self, *candidates: Any) -> set[str]:
        for candidate in candidates:
            if isinstance(candidate, list):
                return {str(x) for x in candidate}
        return set()

    def _schema_fields(self, schema: dict[str, Any], required_names: list[str]) -> list[ParamRow]:
        rows: list[ParamRow] = []
        properties = schema.get("properties") or {}
        required_set = self._as_required_set(required_names, schema.get("required"))
        for name, prop in properties.items():
            prop = self.resolver.resolve(prop)
            rows.append(
                ParamRow(
                    name=name,
                    location="form",
                    type=self._schema_type_label(prop),
                    required="✅" if name in required_set else "❌",
                    description=str(prop.get("description") or prop.get("title") or "—"),
                )
            )
        return rows

    def _responses(self, responses: dict[str, Any]) -> list[ResponseRow]:
        rows: list[ResponseRow] = []
        for status in sorted(responses.keys(), key=lambda s: (s != "default", s)):
            item = responses[status]
            if not isinstance(item, dict):
                continue
            description = str(item.get("description") or "—")
            example = "{}"
            content = item.get("content") or {}
            json_content = content.get("application/json") or content.get("*/*")
            if json_content:
                schema = self.resolver.resolve(json_content.get("schema", {}))
                ex = self._example_from_schema(schema)
                example = json.dumps(ex, ensure_ascii=False)
                if len(example) > 120:
                    example = example[:117] + "..."
            rows.append(ResponseRow(status=status, description=description, example=example))
        return rows

    def _schema_type_label(self, schema: dict[str, Any]) -> str:
        if "$ref" in schema:
            ref = schema["$ref"]
            return ref.rsplit("/", 1)[-1]
        if "anyOf" in schema:
            return " | ".join(self._schema_type_label(self.resolver.resolve(s)) for s in schema["anyOf"])
        schema_type = schema.get("type")
        if schema_type == "array":
            items = schema.get("items", {"type": "any"})
            return f"array[{self._schema_type_label(self.resolver.resolve(items))}]"
        if schema_type:
            fmt = schema.get("format")
            return f"{schema_type} ({fmt})" if fmt else str(schema_type)
        if "enum" in schema:
            return "enum"
        return "any"

    def _example_from_schema(self, schema: dict[str, Any], depth: int = 0) -> Any:
        if depth > 12:
            return None
        schema = self.resolver.resolve(schema)

        if "example" in schema:
            return schema["example"]
        if "default" in schema:
            return schema["default"]
        if "enum" in schema and schema["enum"]:
            return schema["enum"][0]

        if "anyOf" in schema:
            for option in schema["anyOf"]:
                if option.get("type") == "null":
                    continue
                return self._example_from_schema(option, depth + 1)
            return None

        schema_type = schema.get("type")

        if schema_type == "object" or "properties" in schema:
            result: dict[str, Any] = {}
            required = set(self._as_required_set(schema.get("required")))
            for name, prop in (schema.get("properties") or {}).items():
                if name not in required and depth > 0:
                    continue
                prop = self.resolver.resolve(prop)
                sample = self._example_from_schema(prop, depth + 1)
                result[name] = self._example_for_field(name, prop, sample)
            return result

        if schema_type == "array":
            items = schema.get("items", {"type": "string"})
            return [self._example_from_schema(items, depth + 1)]

        if schema_type in SCHEMA_TYPE_EXAMPLES:
            base = SCHEMA_TYPE_EXAMPLES[schema_type]
            fmt = schema.get("format")
            if schema_type == "string":
                if fmt == "date":
                    return "1980-05-15"
                if fmt == "date-time":
                    return "2026-06-21T12:00:00Z"
                if fmt == "email":
                    return "user@example.com"
                title = schema.get("title", "").lower()
                if "phone" in title or "phone" in str(schema.get("description", "")).lower():
                    return "+1234567890"
                return "string"
            return base

        return None

    def _example_for_field(self, name: str, prop: dict[str, Any], sample: Any) -> Any:
        lowered = name.lower()
        if lowered in {"first_name", "firstname"}:
            return "John"
        if lowered in {"last_name", "lastname"}:
            return "Doe"
        if lowered == "gender":
            return "M"
        if lowered == "middle_name":
            return None
        if "enum" in prop and prop["enum"]:
            return prop["enum"][0]
        return sample

    def _curl_example(
        self,
        method: str,
        path: str,
        body_json: str | None,
        form_fields: list[ParamRow] | None,
    ) -> str:
        url = f"{CURL_EXAMPLE_HOST.rstrip('/')}{path}"
        lines = [f"curl -X {method} {url} \\"]

        if body_json and method in {"POST", "PUT", "PATCH"}:
            lines.append('  -H "Authorization: Bearer $JWT" \\')
            lines.append('  -H "Content-Type: application/json" \\')
            compact = json.dumps(json.loads(body_json), ensure_ascii=False, separators=(",", ":"))
            escaped = compact.replace("'", "'\\''")
            lines.append(f"  -d '{escaped}'")
        elif form_fields and method in {"POST", "PUT", "PATCH"}:
            lines.append('  -H "Authorization: Bearer $JWT" \\')
            for fld in form_fields[:6]:
                if fld.type.startswith("array") or fld.type == "object":
                    continue
                sample = "file.pdf" if "file" in fld.name.lower() else "value"
                lines.append(f'  -F "{fld.name}={sample}" \\')
            if lines[-1].endswith(" \\"):
                lines[-1] = lines[-1][:-2]
        else:
            lines.append('  -H "Authorization: Bearer $JWT"')
            if lines[-1].endswith(" \\"):
                lines[-1] = lines[-1][:-2]

        return "\n".join(lines)


def load_openapi_from_url(url: str) -> dict[str, Any]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def load_openapi_from_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"OpenAPI file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_openapi_from_app() -> dict[str, Any]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from app.main import app  # noqa: WPS433

    return app.openapi()


def save_openapi_cache(schema: dict[str, Any], path: Path = OPENAPI_CACHE_FILE) -> None:
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_tags(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Markdown API docs from OpenAPI schema")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", default=None, help=f"Fetch OpenAPI JSON (default: {DEFAULT_OPENAPI_URL})")
    source.add_argument("--file", type=Path, default=None, help="Read cached openapi.json file")
    source.add_argument(
        "--import-app",
        action="store_true",
        help="Load schema from app.main:app (no running server required)",
    )
    parser.add_argument("--tags", default=None, help="Comma-separated group slugs to generate")
    parser.add_argument("--cache", action="store_true", help="Write fetched schema to openapi.json")
    parser.add_argument("--update-nav", action="store_true", help="Update mkdocs.yml API nav section")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory")
    args = parser.parse_args(argv)

    output_dir = args.output_dir

    try:
        if args.import_app:
            print("Loading OpenAPI schema from FastAPI app…")
            openapi = load_openapi_from_app()
        elif args.file:
            print(f"Loading OpenAPI schema from {args.file}…")
            openapi = load_openapi_from_file(args.file)
        else:
            url = args.url or DEFAULT_OPENAPI_URL
            print(f"Fetching OpenAPI schema from {url}…")
            openapi = load_openapi_from_url(url)

        if args.cache:
            save_openapi_cache(openapi)
            print(f"Cached schema → {OPENAPI_CACHE_FILE}")

        tag_filter = parse_tags(args.tags)
        generator = OpenAPIDocGenerator(openapi)
        written = generator.generate(tag_filter=tag_filter, output_dir=output_dir)

        print(f"Generated {len(written)} file(s) in {output_dir}:")
        for slug, path in sorted(written.items()):
            print(f"  • {path.relative_to(PROJECT_ROOT)}")

        if args.update_nav:
            from update_mkdocs_nav import update_mkdocs_nav  # noqa: WPS433

            update_mkdocs_nav(written, mkdocs_path=MKDOCS_PATH)
            print(f"Updated navigation → {MKDOCS_PATH}")

    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Hint: run with --import-app or start the server and use --url", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"ERROR: failed to fetch OpenAPI schema: {exc}", file=sys.stderr)
        print("Hint: use --import-app or --file openapi.json", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
