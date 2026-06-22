#!/usr/bin/env python3
"""Update MkDocs navigation for auto-generated API documentation."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from api_docs_config import (
    MKDOCS_PATH,
    OUTPUT_LOCALE_SUFFIX,
    PROJECT_ROOT,
    TAG_GROUPS,
    TEMPLATES_DIR,
)

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _ordered_api_slugs(written: dict[str, Path]) -> list[str]:
    slugs = [s for s in written if s != "index"]
    return sorted(slugs, key=lambda s: int(TAG_GROUPS.get(s, {}).get("order", 999)))


def build_nav_items(written: dict[str, Path]) -> list[str]:
    """Build mkdocs nav entries (without .en suffix — i18n plugin resolves locale files)."""
    items = ["api/index.md"]
    for slug in _ordered_api_slugs(written):
        if slug in TAG_GROUPS:
            items.append(f"api/{slug}.md")
    return items


def update_mkdocs_nav(
    written: dict[str, Path],
    mkdocs_path: Path = MKDOCS_PATH,
) -> None:
    nav_items = build_nav_items(written)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    block = env.get_template("mkdocs_nav.j2").render(
        nav_items=nav_items,
    ).rstrip()

    text = mkdocs_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"  - API:\n(?:    .*\n)*?(?=  - Деплой:|  - Deployment:|\Z)",
        re.MULTILINE,
    )

    if pattern.search(text):
        new_text = pattern.sub(block + "\n", text, count=1)
    else:
        raise RuntimeError("Could not locate API nav section in mkdocs.yml")

    mkdocs_path.write_text(new_text, encoding="utf-8")


def main() -> int:
    api_dir = PROJECT_ROOT / "docs" / "api"
    written: dict[str, Path] = {}
    if (api_dir / f"index{OUTPUT_LOCALE_SUFFIX}.md").is_file():
        written["index"] = api_dir / f"index{OUTPUT_LOCALE_SUFFIX}.md"
    for slug in TAG_GROUPS:
        path = api_dir / f"{slug}{OUTPUT_LOCALE_SUFFIX}.md"
        if path.is_file():
            written[slug] = path

    if not written:
        print("ERROR: no generated API docs found. Run generate_api_docs.py first.", file=sys.stderr)
        return 1

    update_mkdocs_nav(written)
    print(f"Updated {MKDOCS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
