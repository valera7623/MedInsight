"""Appointments calendar API tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from tests.conftest import auth_header, commit, create_patient, create_tenant, create_user


def test_appointments_flow(client, db_session):
    tenant = create_tenant(db_session, name="Appt Clinic", subdomain="appt-clinic")
    doctor = create_user(db_session, tenant=tenant, email="doc@example.com", role="doctor")
    admin = create_user(db_session, tenant=tenant, email="admin@example.com", role="admin")
    patient = create_patient(db_session, tenant=tenant, user=doctor)
    commit(db_session)

    headers = auth_header(admin)
    headers["X-Tenant-ID"] = str(tenant.id)

    types_res = client.get("/api/appointments/types", headers=headers)
    assert types_res.status_code == 200, types_res.text
    types = types_res.json()
    assert types

    start = datetime.utcnow() + timedelta(days=2)
    start = start.replace(hour=10, minute=0, second=0, microsecond=0)
    payload = {
        "patient_id": patient.id,
        "doctor_id": doctor.id,
        "appointment_type_id": types[0]["id"],
        "start_time": start.isoformat(),
        "duration_minutes": types[0]["duration_minutes"],
        "description": "Test appointment",
        "remind_before_minutes": 30,
    }
    create_res = client.post("/api/appointments", json=payload, headers=headers)
    assert create_res.status_code == 201, create_res.text
    appt_id = create_res.json()["id"]

    confirm_res = client.post(f"/api/appointments/{appt_id}/confirm", headers=headers)
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "confirmed"

    day = start.date().isoformat()
    schedule_res = client.get(
        f"/api/appointments/schedule/doctor/{doctor.id}",
        params={"start_date": day, "end_date": day},
        headers=headers,
    )
    assert schedule_res.status_code == 200
    assert schedule_res.json()["total"] >= 1

    ics_res = client.get("/api/appointments/export/ics", headers=headers)
    assert ics_res.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_res.text

    complete_res = client.post(
        f"/api/appointments/{appt_id}/complete",
        json={"notes": "Done"},
        headers=headers,
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "completed"
