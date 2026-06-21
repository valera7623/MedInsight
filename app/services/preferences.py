"""User preferences service (theme / dark mode)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import UserPreference

VALID_THEMES = frozenset({"light", "dark", "system"})
DEFAULT_THEME = "light"


def normalize_theme(theme: str | None) -> str:
    value = (theme or settings.DEFAULT_THEME or DEFAULT_THEME).strip().lower()
    if value not in VALID_THEMES:
        return DEFAULT_THEME
    return value


def get_or_create_preferences(db: Session, user_id: int) -> UserPreference:
    row = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if row:
        return row
    default = normalize_theme(settings.DEFAULT_THEME)
    row = UserPreference(
        user_id=user_id,
        theme=default if default != "system" else "system",
        system_theme=default == "system",
        settings={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_preferences(db: Session, user_id: int) -> UserPreference:
    return get_or_create_preferences(db, user_id)


def update_preferences(db: Session, user_id: int, *, theme: str | None = None, settings_patch: dict | None = None) -> UserPreference:
    row = get_or_create_preferences(db, user_id)
    if theme is not None:
        normalized = normalize_theme(theme)
        row.theme = normalized
        row.system_theme = normalized == "system"
    if settings_patch is not None:
        merged = dict(row.settings or {})
        merged.update(settings_patch)
        row.settings = merged
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def update_theme(db: Session, user_id: int, theme: str) -> UserPreference:
    return update_preferences(db, user_id, theme=theme)


def preferences_payload(row: UserPreference) -> dict:
    return {
        "theme": row.theme,
        "system_theme": row.system_theme,
        "settings": row.settings or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
