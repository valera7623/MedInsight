"""PostgreSQL production migration: JSONB, FTS, UUID, audit triggers, indexes."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

MIGRATION_ID = "019_migrate_to_postgresql"


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    ).fetchall()
    return bool(rows)


def _index_exists(conn, index_name: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": index_name},
    ).fetchone()
    return row is not None


def _trigger_exists(conn, trigger_name: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM pg_trigger WHERE tgname = :name"),
        {"name": trigger_name},
    ).fetchone()
    return row is not None


def _add_uuid_column(conn, table: str) -> None:
    if not _column_exists(conn, table, "public_id"):
        conn.execute(
            text(
                f"ALTER TABLE {table} "
                "ADD COLUMN public_id UUID NOT NULL DEFAULT gen_random_uuid()"
            )
        )
        idx = f"ix_{table}_public_id"
        if not _index_exists(conn, idx):
            conn.execute(text(f"CREATE UNIQUE INDEX {idx} ON {table} (public_id)"))


def _convert_json_to_jsonb(conn, table: str, column: str) -> None:
    if not _column_exists(conn, table, column):
        return
    row = conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    ).fetchone()
    if row and row[0] == "jsonb":
        return
    conn.execute(
        text(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN {column} TYPE JSONB USING {column}::jsonb"
        )
    )


def _setup_patient_fts(conn) -> None:
    if not _column_exists(conn, "patients", "search_vector"):
        conn.execute(text("ALTER TABLE patients ADD COLUMN search_vector TSVECTOR"))

    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION patients_search_vector_update() RETURNS trigger AS $$
            BEGIN
              NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.first_name, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.last_name, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.middle_name, '')), 'B');
              RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
            """
        )
    )
    if not _trigger_exists(conn, "trg_patients_search_vector"):
        conn.execute(
            text(
                "CREATE TRIGGER trg_patients_search_vector "
                "BEFORE INSERT OR UPDATE ON patients "
                "FOR EACH ROW EXECUTE FUNCTION patients_search_vector_update()"
            )
        )
    conn.execute(text("UPDATE patients SET first_name = first_name WHERE search_vector IS NULL"))

    if not _index_exists(conn, "ix_patients_search_vector_gin"):
        conn.execute(
            text("CREATE INDEX ix_patients_search_vector_gin ON patients USING GIN (search_vector)")
        )


def _setup_document_fts(conn) -> None:
    if not _column_exists(conn, "documents", "search_vector"):
        conn.execute(text("ALTER TABLE documents ADD COLUMN search_vector TSVECTOR"))

    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
            BEGIN
              NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.filename, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.parsed_data::text, '')), 'B');
              RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
            """
        )
    )
    if not _trigger_exists(conn, "trg_documents_search_vector"):
        conn.execute(
            text(
                "CREATE TRIGGER trg_documents_search_vector "
                "BEFORE INSERT OR UPDATE ON documents "
                "FOR EACH ROW EXECUTE FUNCTION documents_search_vector_update()"
            )
        )
    conn.execute(text("UPDATE documents SET filename = filename WHERE search_vector IS NULL"))

    if not _index_exists(conn, "ix_documents_search_vector_gin"):
        conn.execute(
            text("CREATE INDEX ix_documents_search_vector_gin ON documents USING GIN (search_vector)")
        )


def _setup_dicom_fts(conn) -> None:
    if not _column_exists(conn, "dicom_studies", "search_vector"):
        conn.execute(text("ALTER TABLE dicom_studies ADD COLUMN search_vector TSVECTOR"))

    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION dicom_studies_search_vector_update() RETURNS trigger AS $$
            BEGIN
              NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.study_description, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.modality, '')), 'B');
              RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
            """
        )
    )
    if not _trigger_exists(conn, "trg_dicom_studies_search_vector"):
        conn.execute(
            text(
                "CREATE TRIGGER trg_dicom_studies_search_vector "
                "BEFORE INSERT OR UPDATE ON dicom_studies "
                "FOR EACH ROW EXECUTE FUNCTION dicom_studies_search_vector_update()"
            )
        )
    conn.execute(
        text("UPDATE dicom_studies SET study_description = study_description WHERE search_vector IS NULL")
    )

    if not _index_exists(conn, "ix_dicom_studies_search_vector_gin"):
        conn.execute(
            text(
                "CREATE INDEX ix_dicom_studies_search_vector_gin "
                "ON dicom_studies USING GIN (search_vector)"
            )
        )


def _setup_audit_trigger(conn) -> None:
    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION audit_log_trigger() RETURNS trigger AS $$
            DECLARE
              payload JSONB;
            BEGIN
              payload := jsonb_build_object(
                'table', TG_TABLE_NAME,
                'operation', TG_OP,
                'old', CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN row_to_json(OLD)::jsonb ELSE NULL END,
                'new', CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN row_to_json(NEW)::jsonb ELSE NULL END
              );
              INSERT INTO audit_logs (action, resource_type, resource_id, details, created_at, export_status, export_attempts)
              VALUES (
                lower(TG_OP),
                TG_TABLE_NAME,
                COALESCE(
                  CASE WHEN TG_OP = 'DELETE' THEN (OLD.id)::int ELSE (NEW.id)::int END,
                  NULL
                ),
                payload,
                NOW() AT TIME ZONE 'utc',
                'pending',
                0
              );
              RETURN COALESCE(NEW, OLD);
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )

    for table in ("patients", "documents"):
        trigger_name = f"trg_audit_{table}"
        if not _trigger_exists(conn, trigger_name):
            conn.execute(
                text(
                    f"CREATE TRIGGER {trigger_name} "
                    f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION audit_log_trigger()"
                )
            )


def _add_performance_indexes(conn) -> None:
    indexes = [
        ("ix_documents_patient_status", "documents", "(patient_id, status)"),
        ("ix_patients_tenant_last_name", "patients", "(tenant_id, last_name)"),
        ("ix_dicom_studies_patient_modality", "dicom_studies", "(patient_id, modality)"),
        ("ix_analysis_jobs_status_created", "analysis_jobs", "(status, created_at)"),
        ("ix_audit_logs_tenant_created", "audit_logs", "(tenant_id, created_at)"),
    ]
    for idx_name, table, cols in indexes:
        if not _index_exists(conn, idx_name):
            conn.execute(text(f"CREATE INDEX {idx_name} ON {table} {cols}"))


def upgrade(engine: Engine) -> None:
    """Apply PostgreSQL-specific schema upgrades (idempotent)."""
    if engine.dialect.name != "postgresql":
        logger.debug("Skipping %s: dialect is %s", MIGRATION_ID, engine.dialect.name)
        return

    inspector = inspect(engine)
    if not inspector.get_table_names():
        logger.info("%s: no tables yet (fresh DB)", MIGRATION_ID)
        return

    logger.info("Applying %s …", MIGRATION_ID)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

        for table in ("tenants", "users", "patients", "documents"):
            if table in inspector.get_table_names():
                _add_uuid_column(conn, table)

        jsonb_columns = [
            ("tenants", "settings"),
            ("documents", "parsed_data"),
            ("preferences", "settings"),
            ("dicom_annotations", "coordinates"),
            ("audit_logs", "details"),
            ("analysis_jobs", "result"),
            ("predictions", "features"),
            ("predictions", "prediction"),
            ("predictions", "probabilities"),
            ("dicom_studies", "radiology_findings"),
            ("dicom_studies", "extracted_measurements"),
            ("dicom_frames", "pixel_spacing"),
            ("annotation_history", "before_state"),
            ("annotation_history", "after_state"),
            ("error_fixes", "solution_code"),
            ("webhooks", "events"),
            ("telegram_users", "subscription_events"),
        ]
        for table, column in jsonb_columns:
            if table in inspector.get_table_names():
                _convert_json_to_jsonb(conn, table, column)

        if "patients" in inspector.get_table_names():
            _setup_patient_fts(conn)
        if "documents" in inspector.get_table_names():
            _setup_document_fts(conn)
        if "dicom_studies" in inspector.get_table_names():
            _setup_dicom_fts(conn)
        if "audit_logs" in inspector.get_table_names():
            _setup_audit_trigger(conn)

        _add_performance_indexes(conn)

    logger.info("%s applied successfully", MIGRATION_ID)
