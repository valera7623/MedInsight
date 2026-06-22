"""Shared entry points for documentation tooling."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ensure_project_root() -> Path:
    return PROJECT_ROOT
