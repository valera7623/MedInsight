#!/usr/bin/env python3
"""Merge .env with .env.example — add missing keys, preserve existing values."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value
    return data


def merge_env(example_path: Path, env_path: Path) -> tuple[int, int, Path]:
    if not example_path.exists():
        raise FileNotFoundError(f"{example_path} not found")

    existing = parse_env(env_path)
    if env_path.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = env_path.with_name(f".env.backup.{stamp}")
        shutil.copy(env_path, backup)
    else:
        backup = env_path

    example_keys = set(parse_env(example_path).keys())
    added = 0
    preserved = 0
    out_lines: list[str] = []

    for line in example_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out_lines.append(line)
            continue
        key, _, _default = line.partition("=")
        key = key.strip()
        if key in existing:
            out_lines.append(f"{key}={existing[key]}")
            preserved += 1
        else:
            out_lines.append(line)
            added += 1

    extras = sorted((k, v) for k, v in existing.items() if k not in example_keys)
    if extras:
        out_lines.extend(["", "# --- Custom (not in .env.example) ---"])
        for key, value in extras:
            out_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return preserved, added, backup


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    example = root / ".env.example"
    env = root / ".env"
    preserved, added, backup = merge_env(example, env)
    if env.exists() and backup != env:
        print(f"Backup: {backup.name}")
    print(f"Updated {env}: preserved {preserved} keys, added {added} from .env.example")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
