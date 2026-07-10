"""Tenant isolation tests."""

from tests.conftest import auth_header, commit, create_patient, create_tenant, create_user


def test_user_cannot_read_other_tenant_patient(client, db_session):
    tenant_a = create_tenant(db_session, name="A", subdomain="iso-a")
    tenant_b = create_tenant(db_session, name="B", subdomain="iso-b")
    user_a = create_user(db_session, tenant=tenant_a, email="a@example.com", role="doctor")
    user_b = create_user(db_session, tenant=tenant_b, email="b@example.com", role="doctor")
    patient_b = create_patient(db_session, tenant=tenant_b, user=user_b, last_name="Secret")
    commit(db_session)

    res = client.get(f"/api/patients/{patient_b.id}", headers=auth_header(user_a))
    assert res.status_code in (403, 404)


def test_tenant_header_spoof_does_not_leak_patients(client, db_session):
    tenant_a = create_tenant(db_session, name="Spoof A", subdomain="spoof-a")
    tenant_b = create_tenant(db_session, name="Spoof B", subdomain="spoof-b")
    user_a = create_user(db_session, tenant=tenant_a, email="spoof@example.com", role="doctor")
    create_patient(db_session, tenant=tenant_b, user=create_user(db_session, tenant=tenant_b, email="b2@example.com"))
    commit(db_session)

    headers = auth_header(user_a)
    headers["X-Tenant-ID"] = str(tenant_b.id)
    res = client.get("/api/patients", headers=headers)
    assert res.status_code == 200
    body = res.json()
    items = body["items"] if isinstance(body, dict) and "items" in body else body
    for item in items:
        assert item["tenant_id"] == tenant_a.id
