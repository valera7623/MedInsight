#!/usr/bin/env python3
"""Tests for dark mode preferences API and theme normalization."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"


def test_normalize_theme() -> None:
    from app.services.preferences import normalize_theme

    assert normalize_theme("dark") == "dark"
    assert normalize_theme("LIGHT") == "light"
    assert normalize_theme("system") == "system"
    assert normalize_theme("invalid") == "light"
    print("PASS normalize_theme")


def test_preferences_crud() -> None:
    from app.database import Base, SessionLocal, engine
    from app.models import Tenant, User, UserPreference
    from app.auth import hash_password
    from app.services.preferences import get_preferences, update_theme, update_preferences

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        tenant = Tenant(name="T", subdomain="theme-test", settings={}, is_active=True)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        user = User(
            tenant_id=tenant.id,
            email="theme@example.com",
            password_hash=hash_password("secret"),
            full_name="Theme User",
            role="doctor",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        row = get_preferences(db, user.id)
        assert isinstance(row, UserPreference)
        assert row.theme == "light"

        row = update_theme(db, user.id, "dark")
        assert row.theme == "dark"
        assert row.system_theme is False

        row = update_theme(db, user.id, "system")
        assert row.theme == "system"
        assert row.system_theme is True

        row = update_preferences(db, user.id, settings_patch={"dashboard_compact": True})
        assert row.settings.get("dashboard_compact") is True
        print("PASS preferences CRUD")
    finally:
        db.close()


def test_preferences_api() -> None:
    from fastapi.testclient import TestClient
    from app.database import Base, SessionLocal, engine, bootstrap_system
    from app.models import User
    from app.auth import hash_password, create_access_token
    from app.main import app

    Base.metadata.create_all(bind=engine)
    bootstrap_system()
    db = SessionLocal()
    user = User(
        tenant_id=1,
        email="api-theme@example.com",
        password_hash=hash_password("x"),
        full_name="API Theme",
        role="doctor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user)
    db.close()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/preferences", headers=headers)
    assert r.status_code == 200
    assert r.json()["theme"] == "light"

    r = client.put("/api/preferences/theme", headers=headers, json={"theme": "dark"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "updated"
    assert body["theme"] == "dark"

    r = client.get("/api/preferences", headers=headers)
    assert r.json()["theme"] == "dark"
    print("PASS preferences API")


def main() -> None:
    test_normalize_theme()
    test_preferences_crud()
    test_preferences_api()
    print("\nAll theme tests passed.")


if __name__ == "__main__":
    main()
