#!/usr/bin/env python3
"""Test FHIR round-trip: create patient, export, import, verify integrity."""

from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.fhir.fhir_models import Patient, fhir_dump  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Department, Patient as PatientModel, Tenant, User  # noqa: E402
from app.services.fhir.exporter import FhirExporter, _patient_dict  # noqa: E402
from app.services.fhir.importer import FhirImporter  # noqa: E402
from app.services.fhir.mapper import FhirMapper  # noqa: E402


def _ensure_fixtures(db) -> tuple[int, int]:
    tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
    if not tenant:
        tenant = Tenant(name="FHIR Test Clinic", subdomain="fhir-test", settings={}, is_active=True)
        db.add(tenant)
        db.flush()
    dept = db.query(Department).filter(Department.tenant_id == tenant.id).first()
    if not dept:
        dept = Department(tenant_id=tenant.id, name="General")
        db.add(dept)
        db.flush()
    user = db.query(User).filter(User.tenant_id == tenant.id).first()
    if not user:
        user = User(
            tenant_id=tenant.id,
            email=f"fhir-test-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            full_name="FHIR Tester",
            role="admin",
            email_verified=True,
        )
        db.add(user)
        db.flush()
    return tenant.id, user.id


def main() -> int:
    print("=== MedInsight FHIR Round-Trip Test ===")
    print(f"FHIR_ENABLED={settings.FHIR_ENABLED} FHIR_VERSION={settings.FHIR_VERSION}")

    db = SessionLocal()
    try:
        tenant_id, user_id = _ensure_fixtures(db)
        db.commit()

        patient = PatientModel(
            tenant_id=tenant_id,
            user_id=user_id,
            department_id=db.query(Department).filter(Department.tenant_id == tenant_id).first().id,
            first_name="Ivan",
            last_name="Petrov",
            middle_name="Sergeevich",
            birth_date=date(1985, 3, 15),
            gender="M",
            phone="+79001234567",
            email="ivan.petrov@example.com",
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
        print(f"Created MedInsight patient id={patient.id} public_id={patient.public_id}")

        exporter = FhirExporter(db)
        fhir_patient = exporter.export_patient(patient.id)
        print(f"Exported FHIR Patient id={fhir_patient.id} name={fhir_patient.name[0].family}")

        fhir_json = fhir_dump(fhir_patient)
        roundtrip = Patient(**fhir_json)
        importer = FhirImporter(db)
        imported = importer.import_patient(roundtrip, tenant_id=tenant_id, user_id=user_id)
        print(f"Imported FHIR patient -> MedInsight id={imported['id']} fhir_id={imported['fhir_id']}")

        reloaded = db.get(PatientModel, imported["id"])
        checks = {
            "first_name": reloaded.first_name == patient.first_name,
            "last_name": reloaded.last_name == patient.last_name,
            "birth_date": reloaded.birth_date == patient.birth_date,
            "gender": reloaded.gender == patient.gender,
        }
        mapper_ok = FhirMapper.from_fhir_patient(fhir_patient)["last_name"] == "Petrov"
        checks["mapper"] = mapper_ok

        bundle = exporter.export_patient_bundle(patient.id)
        entry_count = len(bundle.entry or [])
        print(f"Patient bundle entries: {entry_count}")

        all_ok = all(checks.values())
        print("Integrity checks:", checks)
        print("RESULT:", "PASS" if all_ok else "FAIL")
        return 0 if all_ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
