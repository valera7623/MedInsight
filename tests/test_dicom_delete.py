"""DICOM study deletion API tests."""

from datetime import datetime

from app.auth import create_access_token, hash_password
from app.database import Base, SessionLocal, bootstrap_system, engine
from app.models import DicomStudy, Patient, Tenant, User


def _seed_user_and_patient(db):
    tenant = Tenant(name="DICOM Del Tenant", subdomain="dicom-del", is_active=True)
    db.add(tenant)
    db.flush()
    user = User(
        email="dicom-del@example.com",
        password_hash=hash_password("secret"),
        role="admin",
        tenant_id=tenant.id,
        full_name="DICOM Admin",
    )
    db.add(user)
    db.flush()
    patient = Patient(
        tenant_id=tenant.id,
        user_id=user.id,
        first_name="Test",
        last_name="Patient",
        birth_date=datetime(1990, 1, 1).date(),
        gender="M",
    )
    db.add(patient)
    db.commit()
    db.refresh(user)
    db.refresh(patient)
    return user, patient


def test_delete_failed_pending_study_by_id():
    from fastapi.testclient import TestClient

    from app.main import app

    Base.metadata.create_all(bind=engine)
    bootstrap_system()
    db = SessionLocal()
    try:
        user, patient = _seed_user_and_patient(db)
        study = DicomStudy(
            patient_id=patient.id,
            tenant_id=patient.tenant_id,
            user_id=user.id,
            study_uid="pending-deadbeef",
            status="failed",
            error_message="parse error",
            num_series=0,
            num_instances=0,
        )
        db.add(study)
        db.commit()
        db.refresh(study)
        study_id = study.id
        token = create_access_token(user)
    finally:
        db.close()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.delete(f"/api/dicom/studies/by-id/{study_id}", headers=headers)
    assert response.status_code == 204, response.text

    db = SessionLocal()
    try:
        assert db.query(DicomStudy).filter(DicomStudy.id == study_id).first() is None
    finally:
        db.close()
