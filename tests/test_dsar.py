"""Tests for DSAR export API."""

from tests.conftest import auth_header, commit, create_patient, create_tenant, create_user


def test_dsar_export_patient(client, db_session):
    tenant = create_tenant(db_session, name="DSAR", subdomain="dsar")
    admin = create_user(db_session, tenant=tenant, email="admin@dsar.com", role="admin", password="ValidPass1!")
    doctor = create_user(db_session, tenant=tenant, email="doc@dsar.com", role="doctor", password="ValidPass1!")
    patient = create_patient(db_session, tenant=tenant, user=doctor)
    commit(db_session)

    res = client.get(
        f"/api/admin/dsar/patients/{patient.id}/export",
        headers=auth_header(admin),
    )
    assert res.status_code == 200
    assert "patient" in res.text
