"""MFA policy tests."""

from app.config import settings
from app.models import Tenant, User
from app.services import mfa_policy


def test_parse_role_list():
    assert mfa_policy._parse_role_list("admin, doctor") == {"admin", "doctor"}
    assert mfa_policy._parse_role_list("") == set()


def test_mfa_disabled_when_enforced_off(monkeypatch):
    monkeypatch.setattr(settings, "MFA_ENFORCED", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    user = User(id=1, email="a@b.com", role="super_admin", totp_enabled=False)
    assert mfa_policy.mfa_required_for_user(user, None) is False
