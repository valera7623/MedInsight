"""Collect scoped rows for Excel export (shared by route + Celery task)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Query, Session

from app.models import AuditLog, Document, Patient, Prediction, User
from app.services.list_queries import (
    audit_scope,
    departments_scope,
    documents_scope,
    patients_scope,
    predictions_scope,
    users_scope,
)

_MODELS = {
    "patients": Patient,
    "documents": Document,
    "predictions": Prediction,
    "users": User,
    "audit": AuditLog,
}


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def _scoped_query(db: Session, entity: str, user: User, tenant_id: int | None) -> Query:
    if entity == "patients":
        return patients_scope(db, user, tenant_id)
    if entity == "documents":
        return documents_scope(db, user, tenant_id)
    if entity == "predictions":
        return predictions_scope(db, user, tenant_id)
    if entity == "users":
        return users_scope(db, user, tenant_id)
    if entity == "departments":
        return departments_scope(db, user, tenant_id)
    if entity == "audit":
        return audit_scope(db, user, tenant_id)
    raise ValueError(f"Unknown export entity: {entity}")


def _apply_filters(query: Query, entity: str, filters: dict[str, Any]) -> Query:
    model = _MODELS.get(entity)
    filters = filters or {}

    # Special-cased filters.
    if entity == "users" and "is_active" in filters and filters["is_active"] is not None:
        query = query.filter(User.is_blocked.is_(not bool(filters["is_active"])))
    if entity == "audit":
        dt_from = _parse_date(filters.get("from_date"))
        dt_to = _parse_date(filters.get("to_date"))
        if dt_from:
            query = query.filter(AuditLog.created_at >= dt_from)
        if dt_to:
            query = query.filter(AuditLog.created_at <= dt_to)

    skip = {"is_active", "from_date", "to_date", "search"}
    for key, value in filters.items():
        if key in skip or value is None or model is None:
            continue
        column = getattr(model, key, None)
        if column is not None:
            query = query.filter(column == value)
    return query


def count_export_rows(db: Session, entity: str, user: User, tenant_id: int | None, filters: dict) -> int:
    return _apply_filters(_scoped_query(db, entity, user, tenant_id), entity, filters).count()


def collect_export_rows(
    db: Session, entity: str, user: User, tenant_id: int | None, filters: dict, max_rows: int
) -> list:
    query = _apply_filters(_scoped_query(db, entity, user, tenant_id), entity, filters)
    model = _MODELS.get(entity)
    if model is not None and hasattr(model, "created_at"):
        query = query.order_by(model.created_at.desc())
    return query.limit(max_rows).all()
