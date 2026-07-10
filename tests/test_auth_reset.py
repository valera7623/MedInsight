"""Password reset flow tests."""

from app.auth import create_email_token, verify_password
from tests.conftest import commit, create_tenant, create_user


def test_reset_password_happy_path(client, db_session):
    tenant = create_tenant(db_session, name="Reset Clinic", subdomain="reset-clinic")
    user = create_user(db_session, tenant=tenant, email="reset@example.com", role="doctor")
    commit(db_session)

    token = create_email_token(user.email, "reset", 2, tenant_id=user.tenant_id)
    res = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassword99"},
    )
    assert res.status_code == 200, res.text

    db_session.refresh(user)
    assert verify_password("newpassword99", user.password_hash)
    assert not verify_password("password123", user.password_hash)


def test_reset_password_invalid_token(client):
    res = client.post(
        "/api/auth/reset-password",
        json={"token": "not-a-valid-token", "new_password": "newpassword99"},
    )
    assert res.status_code == 400


def test_request_reset_always_accepted(client, db_session):
    tenant = create_tenant(db_session, name="Req Clinic", subdomain="req-clinic")
    create_user(db_session, tenant=tenant, email="exists@example.com")
    commit(db_session)

    res = client.post(
        "/api/auth/request-reset",
        json={"email": "missing@example.com", "subdomain": tenant.subdomain},
    )
    assert res.status_code == 202

    res2 = client.post(
        "/api/auth/request-reset",
        json={"email": "exists@example.com", "subdomain": tenant.subdomain},
    )
    assert res2.status_code == 202


def test_verify_email_scoped_by_tenant(client, db_session):
    tenant_a = create_tenant(db_session, name="Tenant A", subdomain="tenant-a")
    tenant_b = create_tenant(db_session, name="Tenant B", subdomain="tenant-b")
    user_a = create_user(db_session, tenant=tenant_a, email="same@example.com", role="doctor")
    user_b = create_user(db_session, tenant=tenant_b, email="same@example.com", role="doctor")
    user_a.email_verified = False
    user_b.email_verified = False
    commit(db_session)

    token = create_email_token(user_a.email, "verify", 24, tenant_id=user_a.tenant_id)
    res = client.post(f"/api/auth/verify-email?token={token}")
    assert res.status_code == 200

    db_session.refresh(user_a)
    db_session.refresh(user_b)
    assert user_a.email_verified is True
    assert user_b.email_verified is False
