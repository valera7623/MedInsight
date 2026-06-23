"""Cross-dialect SQLAlchemy column types (SQLite dev, PostgreSQL production)."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, String, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class PortableJSON(TypeDecorator):
    """JSON on SQLite, JSONB on PostgreSQL."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class PortableUUID(TypeDecorator):
    """UUID native type on PostgreSQL, 36-char string on SQLite."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            if isinstance(value, uuid.UUID):
                return value
            return uuid.UUID(str(value))
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class PortableTSVector(TypeDecorator):
    """PostgreSQL tsvector for FTS; plain Text on SQLite (unused)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


def uuid_default() -> uuid.UUID:
    return uuid.uuid4()
