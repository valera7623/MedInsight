"""Timezone-aware UTC helpers for ORM defaults."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Naive UTC datetime for SQLAlchemy DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
