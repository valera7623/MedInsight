"""Baseline schema stamp — existing DBs use legacy migrations until ALEMBIC_ENABLED.

Revision ID: 001_baseline
"""

from alembic import op
import sqlalchemy as sa

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline: schema created by create_all + app/db/migrations on existing deploys.
    # New environments with ALEMBIC_ENABLED=true should run legacy init once, then stamp head.
    pass


def downgrade() -> None:
    pass
