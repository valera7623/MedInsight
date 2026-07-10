"""Seed MedInsight demo tenants, users, patients, documents, predictions, DICOM.

Idempotent by default (skips if demo tenants already exist). Use ``--force`` to wipe
demo tenants and recreate.

Usage (inside app container)::

    PYTHONPATH=/app python -m scripts.seed_demo
    PYTHONPATH=/app python -m scripts.seed_demo --force
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal, bootstrap_system
from app.models import (
    Department,
    DicomFrame,
    DicomSeries,
    DicomStudy,
    Document,
    Patient,
    Prediction,
    Tenant,
    User,
)
from app.services.tenant_deletion import delete_tenant_with_dependencies

ROOT = Path(__file__).resolve().parents[1]
DEMO_DICOM_DIR = ROOT / "demo_data" / "dicom"

DEMO_TENANTS = [
    {"name": "Клиника №1", "subdomain": "clinic-1"},
    {"name": "Клиника №2", "subdomain": "clinic-2"},
]

DEPT_NAMES = ["Терапевтическое", "Кардиологическое", "Неврологическое", "Хирургическое"]

# Shared demo login (viewer on clinic-1) — credentials for Telderi buyers.
DEMO_LOGIN_EMAIL = "demo@medinsight.com"
DEMO_LOGIN_PASSWORD = "demo123"

USERS_SPEC = [
    # (email, full_name, role, tenant_idx, can_see_all)
    (DEMO_LOGIN_EMAIL, "Demo Viewer", "viewer", 0, True),
    ("admin1@medinsight.com", "Админ Клиники 1", "admin", 0, True),
    ("doctor1@medinsight.com", "Иванов Пётр Сергеевич", "doctor", 0, False),
    ("doctor2@medinsight.com", "Петрова Анна Игоревна", "doctor", 0, False),
    ("researcher1@medinsight.com", "Сидоров Илья", "researcher", 0, True),
    ("admin2@medinsight.com", "Админ Клиники 2", "admin", 1, True),
    ("doctor3@medinsight.com", "Козлова Мария", "doctor", 1, False),
    ("viewer2@medinsight.com", "Наблюдатель Клиники 2", "viewer", 1, True),
]

PATIENT_SEED = [
    # last, first, middle, birth, gender, phone, tenant_idx, dept_idx
    ("Смирнов", "Алексей", "Иванович", date(1958, 3, 12), "M", "89001110001", 0, 1),
    ("Кузнецова", "Елена", "Петровна", date(1972, 7, 4), "F", "89001110002", 0, 0),
    ("Попов", "Дмитрий", "Александрович", date(1985, 11, 21), "M", "89001110003", 0, 2),
    ("Васильева", "Ольга", "Сергеевна", date(1990, 1, 8), "F", "89001110004", 0, 0),
    ("Новиков", "Игорь", "Владимирович", date(1949, 9, 30), "M", "89001110005", 0, 1),
    ("Морозова", "Наталья", "Андреевна", date(1965, 5, 17), "F", "89001110006", 0, 2),
    ("Фёдоров", "Сергей", "Николаевич", date(1978, 12, 2), "M", "89001110007", 0, 3),
    ("Волкова", "Ирина", "Олеговна", date(2001, 4, 25), "F", "89001110008", 0, 0),
    ("Алексеев", "Павел", "Юрьевич", date(1955, 8, 14), "M", "89001110009", 1, 1),
    ("Лебедева", "Татьяна", "Михайловна", date(1982, 2, 19), "F", "89001110010", 1, 0),
    ("Семёнов", "Андрей", "Игоревич", date(1970, 6, 7), "M", "89001110011", 1, 2),
    ("Егорова", "Марина", "Васильевна", date(1995, 10, 11), "F", "89001110012", 1, 0),
    ("Павлов", "Никита", "Романович", date(1960, 3, 3), "M", "89001110013", 1, 3),
    ("Козлова", "Светлана", "Дмитриевна", date(1988, 7, 28), "F", "89001110014", 1, 1),
    ("Орлов", "Максим", "Артёмович", date(1975, 1, 15), "M", "89001110015", 1, 2),
]

DIAGNOSES = [
    "I10 Эссенциальная гипертензия",
    "E11.9 Сахарный диабет 2 типа",
    "I25.1 Атеросклеротическая болезнь сердца",
    "J18.9 Пневмония неуточнённая",
    "I63.9 Инфаркт мозга",
    "K29.5 Хронический гастрит",
    "M54.5 Боль внизу спины",
    "N18.3 ХБП 3 стадии",
    "J44.1 ХОБЛ с обострением",
    "I48.0 Пароксизмальная фибрилляция предсердий",
]

MEDICATIONS = [
    "Амлодипин 5 мг",
    "Метформин 1000 мг",
    "Аторвастатин 20 мг",
    "Аспирин 100 мг",
    "Бисопролол 2.5 мг",
    "Омепразол 20 мг",
    "Фуросемид 40 мг",
    "Клопидогрел 75 мг",
]


def _ensure_dicom_pack() -> list[Path]:
    if not DEMO_DICOM_DIR.exists() or not any(DEMO_DICOM_DIR.glob("*/frame_0.png")):
        from scripts.generate_demo_dicom import generate

        generate(DEMO_DICOM_DIR)
    return sorted(p for p in DEMO_DICOM_DIR.iterdir() if p.is_dir())


def _wipe_demo_tenants(db) -> None:
    for spec in DEMO_TENANTS:
        tenant = db.query(Tenant).filter(Tenant.subdomain == spec["subdomain"]).first()
        if tenant:
            print(f"Removing existing demo tenant {spec['subdomain']} (id={tenant.id})")
            delete_tenant_with_dependencies(db, tenant)


def _get_or_create_tenants(db) -> list[Tenant]:
    tenants: list[Tenant] = []
    for spec in DEMO_TENANTS:
        tenant = db.query(Tenant).filter(Tenant.subdomain == spec["subdomain"]).first()
        if not tenant:
            tenant = Tenant(name=spec["name"], subdomain=spec["subdomain"], settings={"demo": True}, is_active=True)
            db.add(tenant)
            db.flush()
            print(f"Created tenant {tenant.subdomain} id={tenant.id}")
        tenants.append(tenant)
    db.commit()
    return tenants


def _seed_departments(db, tenants: list[Tenant]) -> dict[tuple[int, int], Department]:
    mapping: dict[tuple[int, int], Department] = {}
    for t in tenants:
        for i, name in enumerate(DEPT_NAMES):
            dept = (
                db.query(Department)
                .filter(Department.tenant_id == t.id, Department.name == name)
                .first()
            )
            if not dept:
                dept = Department(tenant_id=t.id, name=name)
                db.add(dept)
                db.flush()
            mapping[(t.id, i)] = dept
    db.commit()
    return mapping


def _seed_users(db, tenants: list[Tenant], depts: dict[tuple[int, int], Department]) -> list[User]:
    users: list[User] = []
    for email, full_name, role, t_idx, can_see_all in USERS_SPEC:
        tenant = tenants[t_idx]
        existing = db.query(User).filter(User.tenant_id == tenant.id, User.email == email).first()
        if existing:
            users.append(existing)
            continue
        dept = depts.get((tenant.id, 0)) if role in ("doctor", "head_of_department", "nurse") else None
        password = DEMO_LOGIN_PASSWORD if email == DEMO_LOGIN_EMAIL else "demo123"
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            tenant_id=tenant.id,
            department_id=dept.id if dept else None,
            can_see_all_patients=can_see_all,
            email_verified=True,
            email_verified_at=datetime.utcnow(),
            is_blocked=False,
        )
        db.add(user)
        db.flush()
        users.append(user)
        print(f"Created user {email} ({role}) tenant={tenant.subdomain}")
    db.commit()
    return users


def _seed_patients(
    db, tenants: list[Tenant], depts: dict[tuple[int, int], Department], users: list[User]
) -> list[Patient]:
    # Prefer doctors as owners
    doctors = [u for u in users if u.role == "doctor"]
    patients: list[Patient] = []
    for i, row in enumerate(PATIENT_SEED):
        last, first, middle, birth, gender, phone, t_idx, d_idx = row
        tenant = tenants[t_idx]
        existing = (
            db.query(Patient)
            .filter(
                Patient.tenant_id == tenant.id,
                Patient.last_name == last,
                Patient.first_name == first,
                Patient.birth_date == birth,
            )
            .first()
        )
        if existing:
            patients.append(existing)
            continue
        owner = next((d for d in doctors if d.tenant_id == tenant.id), users[0])
        dept = depts[(tenant.id, d_idx)]
        patient = Patient(
            tenant_id=tenant.id,
            user_id=owner.id,
            department_id=dept.id,
            attending_doctor_id=owner.id if owner.role == "doctor" else None,
            first_name=first,
            last_name=last,
            middle_name=middle,
            birth_date=birth,
            gender=gender,
            phone=phone,
            email=f"patient{i+1}@demo.medinsight.local",
        )
        db.add(patient)
        db.flush()
        patients.append(patient)
    db.commit()
    print(f"Patients ready: {len(patients)}")
    return patients


def _write_doc_file(tenant_id: int, patient_id: int, filename: str, text: str) -> tuple[str, int]:
    base = Path(settings.STORAGE_PATH) / "demo_docs" / f"tenant_{tenant_id}" / f"patient_{patient_id}"
    base.mkdir(parents=True, exist_ok=True)
    path = base / filename
    data = text.encode("utf-8")
    path.write_bytes(data)
    return str(path), len(data)


def _seed_documents(db, patients: list[Patient], users: list[User]) -> list[Document]:
    docs: list[Document] = []
    existing_count = db.query(Document).filter(Document.filename.like("demo_%")).count()
    if existing_count >= 30:
        print(f"Documents already seeded ({existing_count})")
        return db.query(Document).filter(Document.filename.like("demo_%")).all()

    for i in range(30):
        patient = patients[i % len(patients)]
        owner = next((u for u in users if u.tenant_id == patient.tenant_id), users[0])
        dtype = ["discharge", "lab", "history"][i % 3]
        diag = DIAGNOSES[i % len(DIAGNOSES)]
        meds = [MEDICATIONS[i % len(MEDICATIONS)], MEDICATIONS[(i + 3) % len(MEDICATIONS)]]
        filename = f"demo_{dtype}_{patient.id}_{i+1}.txt"
        body = (
            f"Демо-документ ({dtype})\nПациент: {patient.last_name} {patient.first_name}\n"
            f"Диагноз: {diag}\nЛекарства: {', '.join(meds)}\n"
            f"Дата: {(datetime.utcnow() - timedelta(days=i * 3)).date().isoformat()}\n"
        )
        path, size = _write_doc_file(patient.tenant_id, patient.id, filename, body)
        parsed = {
            "diagnoses": [diag],
            "medications": meds,
            "full_text": body,
            "lab_results": [
                {"name": "Глюкоза", "value": str(4.5 + (i % 5) * 0.3), "unit": "ммоль/л"},
                {"name": "Креатинин", "value": str(70 + i), "unit": "мкмоль/л"},
            ]
            if dtype == "lab"
            else [],
        }
        doc = Document(
            tenant_id=patient.tenant_id,
            patient_id=patient.id,
            user_id=owner.id,
            filename=filename,
            file_path=path,
            file_size=size,
            mime_type="text/plain",
            document_type=dtype,
            is_encrypted=False,
            parsed_data=parsed,
            status="parsed",
            parsed_at=datetime.utcnow(),
        )
        db.add(doc)
        docs.append(doc)
    db.commit()
    print(f"Documents created: {len(docs)}")
    return docs


def _seed_predictions(db, patients: list[Patient], users: list[User]) -> None:
    existing = (
        db.query(Prediction)
        .filter(Prediction.type.in_(["readmission", "complication"]))
        .count()
    )
    if existing >= 20:
        print(f"Predictions already present (~{existing})")
        return

    created = 0
    for i in range(20):
        patient = patients[i % len(patients)]
        owner = next((u for u in users if u.tenant_id == patient.tenant_id), users[0])
        ptype = "readmission" if i % 2 == 0 else "complication"
        risk = 0.15 + (i % 10) * 0.07
        pred = Prediction(
            tenant_id=patient.tenant_id,
            patient_id=patient.id,
            user_id=owner.id,
            type=ptype,
            features={"demo": True, "age": 2026 - patient.birth_date.year, "docs": 2},
            prediction={
                "risk_level": "high" if risk > 0.55 else "moderate" if risk > 0.35 else "low",
                "score": risk,
            },
            probabilities={"positive": risk, "negative": 1 - risk},
            confidence_score=round(0.6 + (i % 5) * 0.07, 2),
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db.add(pred)
        created += 1
    db.commit()
    print(f"Predictions created: {created}")


def _seed_dicom(db, patients: list[Patient], users: list[User]) -> None:
    packs = _ensure_dicom_pack()
    existing = db.query(DicomStudy).filter(DicomStudy.study_uid.like("%.demo.%")).count()
    if existing >= 10:
        print(f"DICOM studies already seeded ({existing})")
        return

    storage_base = Path(settings.DICOM_STORAGE_PATH)
    storage_base.mkdir(parents=True, exist_ok=True)
    created = 0
    for idx, pack in enumerate(packs[:10]):
        patient = patients[idx % len(patients)]
        owner = next((u for u in users if u.tenant_id == patient.tenant_id), users[0])
        meta: dict[str, str] = {}
        meta_file = pack / "meta.txt"
        if meta_file.exists():
            for line in meta_file.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    meta[k.strip()] = v.strip()
        study_uid = meta.get("study_uid", f"1.2.826.0.1.3680043.8.498.demo.{idx+1}.1")
        series_uid = meta.get("series_uid", f"1.2.826.0.1.3680043.8.498.demo.{idx+1}.2")
        sop_uid = meta.get("sop_uid", f"1.2.826.0.1.3680043.8.498.demo.{idx+1}.3")
        modality = meta.get("modality", "CT")
        description = meta.get("description", f"Demo {modality}")

        if db.query(DicomStudy).filter(DicomStudy.study_uid == study_uid).first():
            continue

        study_dir = storage_base / str(patient.id) / study_uid.replace("/", "_")
        frames_dir = study_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        src_png = pack / "frame_0.png"
        dest_png = frames_dir / f"{sop_uid.replace('.', '_')}_f0.png"
        if src_png.exists():
            shutil.copy2(src_png, dest_png)
        src_dcm = pack / "sample.dcm"
        dest_dcm = study_dir / "sample.dcm"
        if src_dcm.exists():
            shutil.copy2(src_dcm, dest_dcm)

        study = DicomStudy(
            patient_id=patient.id,
            tenant_id=patient.tenant_id,
            user_id=owner.id,
            study_uid=study_uid,
            study_date=datetime.utcnow() - timedelta(days=idx * 5),
            study_description=description,
            modality=modality,
            body_part={"CT": "CHEST", "MR": "BRAIN", "CR": "CHEST", "DX": "PELVIS", "US": "ABDOMEN"}.get(
                modality, "OTHER"
            ),
            patient_name_dicom=f"{patient.last_name}^{patient.first_name}",
            patient_id_dicom=str(patient.id),
            num_series=1,
            num_instances=1,
            file_path_encrypted=str(dest_dcm) if dest_dcm.exists() else None,
            original_filename="sample.dcm",
            status="ready",
            processed_at=datetime.utcnow(),
            total_files=1,
            processed_files=1,
            radiology_findings=[{"finding": "Демо-заключение", "confidence": 0.8}],
            radiology_impression="Демо-исследование для ознакомления с платформой.",
        )
        db.add(study)
        db.flush()

        series = DicomSeries(
            study_id=study.id,
            series_uid=series_uid,
            series_number=1,
            series_description=description,
            modality=modality,
            num_instances=1,
            original_filename="sample.dcm",
        )
        db.add(series)
        db.flush()

        frame = DicomFrame(
            series_id=series.id,
            instance_uid=sop_uid,
            frame_number=0,
            image_path=str(dest_png),
            width=256,
            height=256,
            bit_depth=8,
        )
        db.add(frame)
        created += 1

    db.commit()
    print(f"DICOM studies created: {created}")


def seed(force: bool = False) -> int:
    bootstrap_system()
    db = SessionLocal()
    try:
        if force:
            _wipe_demo_tenants(db)

        # If demo tenants exist and not forcing, still fill missing pieces.
        tenants = _get_or_create_tenants(db)
        depts = _seed_departments(db, tenants)
        users = _seed_users(db, tenants, depts)
        patients = _seed_patients(db, tenants, depts, users)
        _seed_documents(db, patients, users)
        _seed_predictions(db, patients, users)
        _seed_dicom(db, patients, users)

        print("\nDemo seed complete.")
        print(f"  Login: {DEMO_LOGIN_EMAIL} / {DEMO_LOGIN_PASSWORD}")
        print(f"  Tenant subdomain: {DEMO_TENANTS[0]['subdomain']}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Seed failed: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed MedInsight demo data")
    parser.add_argument("--force", action="store_true", help="Delete and recreate demo tenants")
    args = parser.parse_args(argv)
    return seed(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
