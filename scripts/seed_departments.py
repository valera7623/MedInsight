"""Idempotently create the standard MedInsight departments in a tenant.

Usage (inside the app container):
    PYTHONPATH=/app python scripts/seed_departments.py [tenant_subdomain]

Defaults to the "default" tenant.
"""

from __future__ import annotations

import sys

from app.database import SessionLocal
from app.models import Department, Tenant

NAMES = [
    "Кардиологическое",
    "Неврологическое",
    "Терапевтическое",
    "Реанимационное",
    "Гастроэнтерологическое",
    "Паллиативное",
    "Геронтологическое",
    "Поликлиническое",
    "Хирургическое",
    "Урологическое",
    "Педиатрическое",
    "Травматологическое",
    "Нейрохирургическое",
    "Гинекологическое",
]


def main() -> int:
    subdomain = sys.argv[1] if len(sys.argv) > 1 else "default"
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.subdomain == subdomain).first()
        if not tenant:
            print(f"Tenant '{subdomain}' not found")
            return 1
        created = skipped = 0
        for name in NAMES:
            exists = (
                db.query(Department)
                .filter(Department.tenant_id == tenant.id, Department.name == name)
                .first()
            )
            if exists:
                skipped += 1
                continue
            db.add(Department(tenant_id=tenant.id, name=name))
            created += 1
        db.commit()
        print(f"tenant={tenant.id} created={created} skipped={skipped}")
        for d in (
            db.query(Department)
            .filter(Department.tenant_id == tenant.id)
            .order_by(Department.id)
            .all()
        ):
            print(d.id, d.name)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
