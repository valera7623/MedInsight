"""Full-text search helpers (PostgreSQL tsvector; SQLite LIKE fallback)."""

from __future__ import annotations

from sqlalchemy import String, func, or_
from sqlalchemy.orm import Query

from app.core.database import is_postgresql
from app.models import DicomStudy, Document, Patient


def _sqlite_like(query: str):
    pattern = f"%{query.strip()}%"
    return pattern


def search_patients(db_query: Query, query: str) -> Query:
    """Filter patients by name (FTS on PostgreSQL, ILIKE on SQLite)."""
    q = query.strip()
    if not q:
        return db_query
    if is_postgresql():
        ts_query = func.plainto_tsquery("simple", q)
        return db_query.filter(Patient.search_vector.op("@@")(ts_query))
    pattern = _sqlite_like(q)
    return db_query.filter(
        or_(
            Patient.first_name.ilike(pattern),
            Patient.last_name.ilike(pattern),
            Patient.middle_name.ilike(pattern),
        )
    )


def search_documents(db_query: Query, query: str) -> Query:
    q = query.strip()
    if not q:
        return db_query
    if is_postgresql():
        ts_query = func.plainto_tsquery("simple", q)
        return db_query.filter(Document.search_vector.op("@@")(ts_query))
    pattern = _sqlite_like(q)
    return db_query.filter(
        or_(
            Document.filename.ilike(pattern),
            func.cast(Document.parsed_data, String).ilike(pattern),
        )
    )


def search_dicom_studies(db_query: Query, query: str) -> Query:
    q = query.strip()
    if not q:
        return db_query
    if is_postgresql():
        ts_query = func.plainto_tsquery("simple", q)
        return db_query.filter(DicomStudy.search_vector.op("@@")(ts_query))
    pattern = _sqlite_like(q)
    return db_query.filter(
        or_(
            DicomStudy.study_description.ilike(pattern),
            DicomStudy.modality.ilike(pattern),
        )
    )
