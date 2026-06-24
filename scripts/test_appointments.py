#!/usr/bin/env python3
"""Smoke test for appointments calendar API."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def login() -> dict:
    res = client.post(
        "/api/auth/login",
        json={"email": "admin@medinsight.com", "password": "change_me_super_admin"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    token = data["access_token"]
    tenant_id = data.get("tenant_id") or 1
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}


def main() -> None:
    headers = login()
    print("✓ Login")

    types_res = client.get("/api/appointments/types", headers=headers)
    assert types_res.status_code == 200, types_res.text
    types = types_res.json()
    assert types, "Expected default appointment types"
    print(f"✓ Types loaded ({len(types)})")

    patients_res = client.get("/api/patients?limit=1", headers=headers)
    assert patients_res.status_code == 200
    patients = patients_res.json().get("items", [])
    if not patients:
        print("⚠ No patients — skipping create test")
        return
    patient_id = patients[0]["id"]
    doctor_id = patients[0].get("attending_doctor_id")

    if not doctor_id:
        admin_users = client.get("/api/admin/users?role=doctor&limit=5", headers=headers)
        if admin_users.status_code == 200:
            items = admin_users.json()
            if isinstance(items, list) and items:
                doctor_id = items[0]["id"]
            elif isinstance(items, dict) and items.get("items"):
                doctor_id = items["items"][0]["id"]
    if not doctor_id:
        doctor_id = 1

    start = datetime.utcnow() + timedelta(days=2)
    start = start.replace(hour=10, minute=0, second=0, microsecond=0)
    payload = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "appointment_type_id": types[0]["id"],
        "start_time": start.isoformat(),
        "duration_minutes": types[0]["duration_minutes"],
        "description": "Test appointment",
        "remind_before_minutes": 30,
    }
    create_res = client.post("/api/appointments", json=payload, headers=headers)
    assert create_res.status_code == 201, create_res.text
    appt = create_res.json()
    appt_id = appt["id"]
    print(f"✓ Created appointment #{appt_id}")

    confirm_res = client.post(f"/api/appointments/{appt_id}/confirm", headers=headers)
    assert confirm_res.status_code == 200, confirm_res.text
    assert confirm_res.json()["status"] == "confirmed"
    print("✓ Confirmed appointment")

    day = start.date().isoformat()
    schedule_res = client.get(
        f"/api/appointments/schedule/doctor/{doctor_id}",
        params={"start_date": day, "end_date": day},
        headers=headers,
    )
    assert schedule_res.status_code == 200, schedule_res.text
    schedule = schedule_res.json()
    assert schedule["total"] >= 1
    print("✓ Doctor schedule OK")

    slots_res = client.get(
        "/api/appointments/schedule/available-slots",
        params={"doctor_id": doctor_id, "date": day},
        headers=headers,
    )
    assert slots_res.status_code == 200, slots_res.text
    print(f"✓ Available slots: {len(slots_res.json().get('slots', []))}")

    ics_res = client.get("/api/appointments/export/ics", headers=headers)
    assert ics_res.status_code == 200, ics_res.text
    assert "BEGIN:VCALENDAR" in ics_res.text
    print("✓ ICS export OK")

    complete_res = client.post(
        f"/api/appointments/{appt_id}/complete",
        json={"notes": "Test complete"},
        headers=headers,
    )
    assert complete_res.status_code == 200, complete_res.text
    assert complete_res.json()["status"] == "completed"
    print("✓ Completed appointment")

    print("\nAll appointment tests passed.")


if __name__ == "__main__":
    main()
