"""Registration security tests."""

from tests.conftest import auth_header, commit, create_department, create_tenant, create_user


def test_cannot_self_register_as_admin(client, db_session):
    tenant = create_tenant(db_session, name="Clinic A", subdomain="clinic-a")
    commit(db_session)

    res = client.post(
        "/api/auth/register",
        json={
            "email": "bad-admin@example.com",
            "password": "password123",
            "full_name": "Bad Admin",
            "role": "admin",
            "subdomain": tenant.subdomain,
        },
    )
    assert res.status_code == 400
    assert "role" in res.json()["detail"].lower()


def test_register_doctor_and_login(client, db_session):
    tenant = create_tenant(db_session, name="Clinic B", subdomain="clinic-b")
    commit(db_session)

    res = client.post(
        "/api/auth/register",
        json={
            "email": "doctor@example.com",
            "password": "password123",
            "full_name": "Dr Test",
            "role": "doctor",
            "subdomain": tenant.subdomain,
        },
    )
    assert res.status_code == 201, res.text

    login = client.post(
        "/api/auth/login",
        json={"email": "doctor@example.com", "password": "password123", "subdomain": tenant.subdomain},
    )
    assert login.status_code == 200
    data = login.json()
    assert data["role"] == "doctor"
    assert "access_token" in data
    assert "refresh_token" in data


def test_register_rejects_short_password(client, db_session):
    tenant = create_tenant(db_session, name="Clinic C", subdomain="clinic-c")
    commit(db_session)

    res = client.post(
        "/api/auth/register",
        json={
            "email": "short@example.com",
            "password": "short1",
            "full_name": "Short Pass",
            "role": "viewer",
            "subdomain": tenant.subdomain,
        },
    )
    assert res.status_code == 422


def test_viewer_cannot_create_patient(client, db_session):
    tenant = create_tenant(db_session, name="Clinic D", subdomain="clinic-d")
    dept = create_department(db_session, tenant=tenant)
    viewer = create_user(db_session, tenant=tenant, email="viewer@example.com", role="viewer")
    commit(db_session)

    res = client.post(
        "/api/patients",
        headers=auth_header(viewer),
        json={
            "first_name": "A",
            "last_name": "B",
            "birth_date": "1990-01-01",
            "gender": "M",
            "phone": "+79001112233",
            "department_id": dept.id,
        },
    )
    assert res.status_code == 403
