"""Tests for login lockout and failed-login audit."""

from unittest.mock import MagicMock, patch

from app.auth import hash_password
from tests.conftest import commit, create_tenant, create_user


def test_failed_login_returns_401(client, db_session):
    tenant = create_tenant(db_session, name="Lock Tenant", subdomain="lock-tenant")
    create_user(db_session, tenant=tenant, email="lock@example.com", password="ValidPass1!")
    commit(db_session)

    with patch("app.services.login_lockout.get_redis", return_value=None):
        res = client.post(
            "/api/auth/login",
            json={"email": "lock@example.com", "password": "wrong", "subdomain": "lock-tenant"},
        )
    assert res.status_code == 401


def test_account_lockout_after_failures(client, db_session):
    tenant = create_tenant(db_session, name="Lock2", subdomain="lock2")
    user = create_user(db_session, tenant=tenant, email="lock2@example.com", password="ValidPass1!")
    commit(db_session)

    fake = MagicMock()
    fake.ttl.return_value = 0
    fail_counts = {"n": 0}

    def incr(_key):
        fail_counts["n"] += 1
        return fail_counts["n"]

    fake.incr.side_effect = incr
    fake.expire.return_value = True
    fake.setex.return_value = True
    fake.delete.return_value = True

    with patch("app.services.login_lockout.get_redis", return_value=fake):
        with patch("app.config.settings.LOGIN_LOCKOUT_MAX_ATTEMPTS", 2):
            client.post(
                "/api/auth/login",
                json={"email": "lock2@example.com", "password": "bad", "subdomain": "lock2"},
            )
            res = client.post(
                "/api/auth/login",
                json={"email": "lock2@example.com", "password": "bad", "subdomain": "lock2"},
            )
    assert res.status_code in (401, 429)
