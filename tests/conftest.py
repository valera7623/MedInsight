"""Shared pytest fixtures for MedInsight API integration tests."""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Configure test environment before app imports that read settings.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("BILLING_ENABLED", "true")
os.environ.setdefault("REDIS_CACHE_ENABLED", "false")
os.environ.setdefault("SELF_HEALING_ENABLED", "false")
os.environ.setdefault("EMAIL_VERIFICATION_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("FHIR_ENABLED", "true")
os.environ.setdefault("ENCRYPTION_ENABLED", "false")

from app.auth import create_access_token, create_email_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Department, Patient, Tenant, User  # noqa: E402


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, lifespan="off") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_tenant(db, *, name: str, subdomain: str) -> Tenant:
    tenant = Tenant(name=name, subdomain=subdomain, is_active=True)
    db.add(tenant)
    db.flush()
    return tenant


def create_user(
    db,
    *,
    tenant: Tenant,
    email: str,
    role: str = "doctor",
    password: str = "password123",
    department: Department | None = None,
) -> User:
    user = User(
        tenant_id=tenant.id,
        department_id=department.id if department else None,
        email=email,
        password_hash=hash_password(password),
        full_name=f"Test {role}",
        role=role,
        email_verified=True,
        email_verified_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    return user


def create_department(db, *, tenant: Tenant, name: str = "Therapy") -> Department:
    dept = Department(tenant_id=tenant.id, name=name)
    db.add(dept)
    db.flush()
    return dept


def create_patient(
    db,
    *,
    tenant: Tenant,
    user: User,
    first_name: str = "Ivan",
    last_name: str = "Ivanov",
) -> Patient:
    patient = Patient(
        tenant_id=tenant.id,
        user_id=user.id,
        department_id=user.department_id,
        first_name=first_name,
        last_name=last_name,
        birth_date=date(1990, 1, 1),
        gender="M",
        phone="+79001234567",
    )
    db.add(patient)
    db.flush()
    return patient


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def commit(db) -> None:
    db.commit()
