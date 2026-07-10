"""Usage limit middleware tenant spoofing tests."""

from unittest.mock import patch

from tests.conftest import auth_header, commit, create_patient, create_tenant, create_user


def test_spoofed_tenant_header_does_not_bypass_limit(client, db_session):
    tenant_a = create_tenant(db_session, name="Limit A", subdomain="limit-a")
    tenant_b = create_tenant(db_session, name="Limit B", subdomain="limit-b")
    user_a = create_user(db_session, tenant=tenant_a, email="limit@example.com", role="doctor")
    patient_a = create_patient(db_session, tenant=tenant_a, user=user_a)
    commit(db_session)

    headers = auth_header(user_a)
    headers["X-Tenant-ID"] = str(tenant_b.id)

    with patch("app.middleware.usage_limit.check_analysis_limit", return_value=False):
        res = client.post(f"/api/analytics/predict/{patient_a.id}", headers=headers)

    assert res.status_code == 402
    assert "лимит" in res.json()["detail"].lower()
