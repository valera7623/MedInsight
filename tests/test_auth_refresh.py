"""JWT refresh and token_version tests."""

from app.auth import create_email_token, create_refresh_token, user_token_version, verify_password
from tests.conftest import auth_header, commit, create_tenant, create_user


def test_refresh_token_returns_new_access_token(client, db_session):
    tenant = create_tenant(db_session, name="Refresh Clinic", subdomain="refresh-clinic")
    user = create_user(db_session, tenant=tenant, email="refresh@example.com")
    commit(db_session)

    login = client.post(
        "/api/auth/login",
        json={"email": "refresh@example.com", "password": "password123", "subdomain": tenant.subdomain},
    )
    assert login.status_code == 200
    refresh = login.json()["refresh_token"]

    res = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["access_token"]
    assert data["refresh_token"]


def test_access_token_rejected_on_refresh_endpoint(client, db_session):
    tenant = create_tenant(db_session, name="Type Clinic", subdomain="type-clinic")
    user = create_user(db_session, tenant=tenant, email="type@example.com")
    commit(db_session)

    login = client.post(
        "/api/auth/login",
        json={"email": "type@example.com", "password": "password123", "subdomain": tenant.subdomain},
    )
    access = login.json()["access_token"]
    res = client.post("/api/auth/refresh", json={"refresh_token": access})
    assert res.status_code == 401


def test_refresh_token_cannot_access_api(client, db_session):
    tenant = create_tenant(db_session, name="NoApi Clinic", subdomain="noapi-clinic")
    user = create_user(db_session, tenant=tenant, email="noapi@example.com")
    commit(db_session)

    refresh = create_refresh_token(user)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert res.status_code == 401


def test_password_reset_invalidates_old_tokens(client, db_session):
    tenant = create_tenant(db_session, name="Revoke Clinic", subdomain="revoke-clinic")
    user = create_user(db_session, tenant=tenant, email="revoke@example.com")
    commit(db_session)

    login = client.post(
        "/api/auth/login",
        json={"email": "revoke@example.com", "password": "password123", "subdomain": tenant.subdomain},
    )
    old_access = login.json()["access_token"]

    token = create_email_token(user.email, "reset", 2, tenant_id=user.tenant_id)
    reset = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassword99"},
    )
    assert reset.status_code == 200

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me.status_code == 401

    db_session.refresh(user)
    assert verify_password("newpassword99", user.password_hash)
    assert user_token_version(user) == 1
