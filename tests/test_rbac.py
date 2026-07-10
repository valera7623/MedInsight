"""RBAC integration tests."""

from tests.conftest import auth_header, commit, create_department, create_tenant, create_user


def test_doctor_can_list_patients(client, db_session):
    tenant = create_tenant(db_session, name="RBAC Clinic", subdomain="rbac-clinic")
    dept = create_department(db_session, tenant=tenant)
    doctor = create_user(db_session, tenant=tenant, email="doc@example.com", role="doctor", department=dept)
    commit(db_session)

    res = client.get("/api/patients", headers=auth_header(doctor))
    assert res.status_code == 200


def test_viewer_cannot_upload_documents(client, db_session):
    tenant = create_tenant(db_session, name="View Clinic", subdomain="view-clinic")
    viewer = create_user(db_session, tenant=tenant, email="view@example.com", role="viewer")
    commit(db_session)

    res = client.post(
        "/api/documents/upload",
        headers=auth_header(viewer),
        data={"patient_id": "1", "document_type": "discharge"},
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 403


def test_admin_endpoints_require_admin(client, db_session):
    tenant = create_tenant(db_session, name="Admin Clinic", subdomain="admin-clinic")
    doctor = create_user(db_session, tenant=tenant, email="notadmin@example.com", role="doctor")
    commit(db_session)

    res = client.get("/api/admin/users", headers=auth_header(doctor))
    assert res.status_code == 403
