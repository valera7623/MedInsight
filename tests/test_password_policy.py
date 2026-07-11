"""Tests for enterprise password policy."""

import pytest

from app.services.password_policy import PasswordPolicyError, validate_password


def test_password_too_short():
    with pytest.raises(PasswordPolicyError):
        validate_password("Short1!")


def test_password_complexity_required(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "PASSWORD_MIN_LENGTH", 8)
    monkeypatch.setattr(settings, "PASSWORD_REQUIRE_COMPLEXITY", True)
    validate_password("ValidPass1!")
    with pytest.raises(PasswordPolicyError):
        validate_password("alllowercase1")
