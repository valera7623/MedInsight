"""User preferences API (theme / dark mode)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.preferences import VALID_THEMES, get_preferences, preferences_payload, update_preferences, update_theme

router = APIRouter(prefix="/preferences", tags=["preferences"])


class ThemeUpdate(BaseModel):
    theme: str = Field(..., pattern="^(light|dark|system)$")


class PreferencesUpdate(BaseModel):
    theme: str | None = Field(None, pattern="^(light|dark|system)$")
    settings: dict[str, Any] | None = None


@router.get("")
def read_preferences(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    row = get_preferences(db, current_user.id)
    return preferences_payload(row)


@router.put("")
def write_preferences(
    body: PreferencesUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if body.theme is not None and body.theme not in VALID_THEMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid theme")
    row = update_preferences(
        db,
        current_user.id,
        theme=body.theme,
        settings_patch=body.settings,
    )
    return {"status": "updated", **preferences_payload(row)}


@router.put("/theme")
def write_theme(
    body: ThemeUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if body.theme not in VALID_THEMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid theme")
    row = update_theme(db, current_user.id, body.theme)
    return {"status": "updated", "theme": row.theme, **preferences_payload(row)}
