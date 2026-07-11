"""Enable PostgreSQL RLS tenant isolation policies."""

from alembic import op

revision = "002_rls"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("patients", "documents", "audit_logs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int
                OR current_setting('app.bypass_rls', true) = 'true'
            )
            """
        )


def downgrade() -> None:
    for table in ("patients", "documents", "audit_logs"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
