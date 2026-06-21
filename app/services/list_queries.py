"""Scoped list queries shared by list endpoints and Excel export.

Each builder returns a SQLAlchemy ``Query`` already restricted to what the given
user may read (tenant + department/patient scope). Search / simple filters /
sorting / pagination are layered on top by ``app.utils.pagination.paginate``.
Date ranges and special filters (e.g. ``is_active``) are handled by callers.
"""

from __future__ import annotations

from sqlalchemy.orm import Query, Session

from app.models import AuditLog, Department, Document, Patient, Prediction, User
from app.services.access import is_super_admin, patients_query

PATIENT_SEARCH_FIELDS = ("first_name", "last_name", "middle_name", "phone", "email")
PATIENT_SORT = ("id", "created_at", "last_name", "first_name", "birth_date")

DOCUMENT_SEARCH_FIELDS = ("filename", "document_type", "status")
DOCUMENT_SORT = ("id", "created_at", "filename", "status", "document_type")

PREDICTION_SORT = ("id", "created_at", "type", "confidence_score")

USER_SEARCH_FIELDS = ("email", "full_name")
USER_SORT = ("id", "created_at", "email", "role")

DEPARTMENT_SEARCH_FIELDS = ("name",)
DEPARTMENT_SORT = ("id", "name")

AUDIT_SORT = ("id", "created_at", "action")


def _accessible_patient_ids(db: Session, user: User, tenant_id: int | None):
    return patients_query(db, user, tenant_id).with_entities(Patient.id)


def patients_scope(db: Session, user: User, tenant_id: int | None) -> Query:
    return patients_query(db, user, tenant_id)


def documents_scope(db: Session, user: User, tenant_id: int | None) -> Query:
    ids = _accessible_patient_ids(db, user, tenant_id)
    return db.query(Document).filter(Document.patient_id.in_(ids))


def predictions_scope(db: Session, user: User, tenant_id: int | None) -> Query:
    ids = _accessible_patient_ids(db, user, tenant_id)
    return db.query(Prediction).filter(Prediction.patient_id.in_(ids))


def users_scope(db: Session, user: User, tenant_id: int | None) -> Query:
    query = db.query(User)
    if is_super_admin(user):
        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)
    else:
        query = query.filter(User.tenant_id == user.tenant_id)
    return query


def departments_scope(db: Session, user: User, tenant_id: int | None) -> Query:
    query = db.query(Department)
    if is_super_admin(user):
        if tenant_id is not None:
            query = query.filter(Department.tenant_id == tenant_id)
    elif user.tenant_id is not None:
        query = query.filter(Department.tenant_id == user.tenant_id)
    else:
        query = query.filter(Department.id.is_(None))  # no tenant -> nothing
    return query


def audit_scope(db: Session, user: User, tenant_id: int | None) -> Query:
    query = db.query(AuditLog)
    if is_super_admin(user):
        if tenant_id is not None:
            query = query.filter(AuditLog.tenant_id == tenant_id)
    else:
        query = query.filter(AuditLog.tenant_id == user.tenant_id)
    return query
