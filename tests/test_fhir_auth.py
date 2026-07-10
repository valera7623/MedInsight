"""FHIR API authentication tests."""

from tests.conftest import auth_header, commit, create_patient, create_tenant, create_user


def test_fhir_patient_search_requires_auth(client, db_session):
    tenant = create_tenant(db_session, name="FHIR Clinic", subdomain="fhir-clinic")
    user = create_user(db_session, tenant=tenant, email="fhir@example.com", role="doctor")
    create_patient(db_session, tenant=tenant, user=user)
    commit(db_session)

    res = client.get("/fhir/Patient")
    assert res.status_code == 401

    authed = client.get("/fhir/Patient", headers=auth_header(user))
    assert authed.status_code == 200


def test_fhir_metadata_is_public(client):
    res = client.get("/fhir/metadata")
    assert res.status_code == 200
    assert res.json().get("resourceType") == "CapabilityStatement"


def test_fhir_viewer_can_read_but_not_create(client, db_session):
    tenant = create_tenant(db_session, name="FHIR View", subdomain="fhir-view")
    viewer = create_user(db_session, tenant=tenant, email="fhir-view@example.com", role="viewer")
    commit(db_session)

    read_res = client.get("/fhir/Patient", headers=auth_header(viewer))
    assert read_res.status_code == 200

    create_res = client.post(
        "/fhir/Patient",
        headers=auth_header(viewer),
        json={
            "resourceType": "Patient",
            "name": [{"family": "Test", "given": ["User"]}],
            "gender": "male",
            "birthDate": "1990-01-01",
        },
    )
    assert create_res.status_code == 403
