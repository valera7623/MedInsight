"""Tests for server-side sessions and logout."""

from unittest.mock import patch

from tests.conftest import auth_header, commit, create_tenant, create_user


def test_logout_revokes_session(client, db_session):
    tenant = create_tenant(db_session, name="Sess", subdomain="sess")
    user = create_user(db_session, tenant=tenant, email="sess@example.com", password="ValidPass1!")
    commit(db_session)

    with patch("app.services.session_store.get_redis", return_value=None):
        login = client.post(
            "/api/auth/login",
            json={"email": "sess@example.com", "password": "ValidPass1!", "subdomain": "sess"},
        )
    assert login.status_code == 200
    data = login.json()
    headers = auth_header(user)
    headers["Authorization"] = f"Bearer {data['access_token']}"

    with patch("app.services.session_store.revoke_session") as revoke:
        res = client.post(
            "/api/auth/logout",
            json={"refresh_token": data.get("refresh_token")},
            headers=headers,
        )
    assert res.status_code == 200
    if data.get("refresh_token"):
        revoke.assert_called_once()
