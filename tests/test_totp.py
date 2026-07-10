"""TOTP 2FA setup, login, and disable tests."""

from __future__ import annotations

import pyotp

from tests.conftest import auth_header, commit, create_tenant, create_user


def test_totp_setup_enable_and_login(client, db_session):
    tenant = create_tenant(db_session, name="TOTP Clinic", subdomain="totp-clinic")
    user = create_user(db_session, tenant=tenant, email="totp@example.com")
    commit(db_session)

    setup = client.get("/api/auth/totp/setup", headers=auth_header(user))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()

    enable = client.post("/api/auth/totp/enable", headers=auth_header(user), json={"code": code})
    assert enable.status_code == 200, enable.text

    db_session.refresh(user)
    assert user.totp_enabled is True

    login_no_code = client.post(
        "/api/auth/login",
        json={"email": "totp@example.com", "password": "password123", "subdomain": tenant.subdomain},
    )
    assert login_no_code.status_code == 200
    assert login_no_code.json().get("totp_required") is True
    assert not login_no_code.json().get("access_token")

    login_ok = client.post(
        "/api/auth/login",
        json={
            "email": "totp@example.com",
            "password": "password123",
            "subdomain": tenant.subdomain,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert login_ok.status_code == 200
    assert login_ok.json()["access_token"]


def test_totp_disable_requires_password(client, db_session):
    tenant = create_tenant(db_session, name="Disable Clinic", subdomain="disable-clinic")
    user = create_user(db_session, tenant=tenant, email="disable@example.com")
    commit(db_session)

    setup = client.get("/api/auth/totp/setup", headers=auth_header(user))
    secret = setup.json()["secret"]
    client.post(
        "/api/auth/totp/enable",
        headers=auth_header(user),
        json={"code": pyotp.TOTP(secret).now()},
    )

    bad = client.post(
        "/api/auth/totp/disable",
        headers=auth_header(user),
        json={"password": "wrong", "code": pyotp.TOTP(secret).now()},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/api/auth/totp/disable",
        headers=auth_header(user),
        json={"password": "password123", "code": pyotp.TOTP(secret).now()},
    )
    assert ok.status_code == 200
    db_session.refresh(user)
    assert user.totp_enabled is False
