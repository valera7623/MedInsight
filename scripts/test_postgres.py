#!/usr/bin/env python3
"""Smoke tests for PostgreSQL connectivity, migrations, and full-text search.

Usage:
    DATABASE_URL=postgresql://... python scripts/test_postgres.py
    python scripts/test_postgres.py --url postgresql://medinsight:pass@localhost:5432/medinsight
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_connection(url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        assert version and "PostgreSQL" in version, f"Unexpected: {version}"
    print(f"✓ Connection OK — {version.split(',')[0]}")


def test_migrations(url: str) -> None:
    from app.core.database import Base, run_migrations
    from sqlalchemy import create_engine, inspect

    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    run_migrations()

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "patients" in tables, "patients table missing"
    assert "documents" in tables, "documents table missing"

    cols = {c["name"] for c in inspector.get_columns("patients")}
    assert "search_vector" in cols or "public_id" in cols, "PostgreSQL migration columns missing"
    print(f"✓ Migrations OK — {len(tables)} tables")


def test_fulltext_search(url: str) -> None:
    from datetime import date, datetime

    from sqlalchemy import create_engine, func, text
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base, run_migrations
    from app.db.search import search_patients
    from app.models import Patient, Tenant, User

    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    run_migrations()
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        tenant = Tenant(name="Test Clinic", subdomain=f"test-{datetime.utcnow().timestamp():.0f}", is_active=True)
        db.add(tenant)
        db.flush()

        user = User(
            tenant_id=tenant.id,
            email=f"test-{datetime.utcnow().timestamp():.0f}@example.com",
            password_hash="x",
            full_name="Test Doctor",
            role="admin",
            email_verified=True,
        )
        db.add(user)
        db.flush()

        patient = Patient(
            tenant_id=tenant.id,
            user_id=user.id,
            first_name="Иван",
            last_name="Петров",
            birth_date=date(1990, 1, 1),
            gender="M",
            phone="+79001234567",
        )
        db.add(patient)
        db.commit()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT search_vector FROM patients WHERE id = :id"),
                {"id": patient.id},
            ).fetchone()
            assert row is not None, "search_vector column missing"

        results = search_patients(db.query(Patient), "Петров").all()
        assert any(p.id == patient.id for p in results), "FTS query returned no match"

        ts = db.query(func.plainto_tsquery("simple", "Петров")).scalar()
        assert ts is not None, "plainto_tsquery failed"
        print("✓ Full-text search OK")
    finally:
        db.rollback()
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test PostgreSQL setup for MedInsight")
    parser.add_argument("--url", default=None, help="PostgreSQL DATABASE_URL")
    args = parser.parse_args()

    url = args.url
    if not url:
        from app.config import settings

        url = settings.DATABASE_URL

    if not url.startswith("postgresql") and not url.startswith("postgres"):
        print(f"ERROR: expected PostgreSQL URL, got: {url}", file=sys.stderr)
        sys.exit(1)

    print(f"Testing {url.split('@')[-1]} …\n")
    test_connection(url)
    test_migrations(url)
    test_fulltext_search(url)
    print("\nAll PostgreSQL checks passed.")


if __name__ == "__main__":
    main()
