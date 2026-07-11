"""Tests for SSO status endpoint."""


def test_sso_disabled_by_default(client):
    res = client.get("/api/auth/sso/status")
    assert res.status_code == 200
    assert res.json()["enabled"] is False
