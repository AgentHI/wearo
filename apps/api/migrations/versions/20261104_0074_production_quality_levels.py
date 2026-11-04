"""Record approved quality levels for each production model release.

Revision ID: 20261104_0074
Revises: 20261104_0073
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0074"
down_revision: str | None = "20261104_0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.production_model_releases
      ADD COLUMN approved_quality_levels jsonb NOT NULL
        DEFAULT '["LOW","MEDIUM","HIGH"]'::jsonb,
      ADD CONSTRAINT ck_production_approved_quality_levels CHECK (
        jsonb_typeof(approved_quality_levels)='array'
        AND jsonb_array_length(approved_quality_levels) BETWEEN 1 AND 3
        AND approved_quality_levels <@ '["LOW","MEDIUM","HIGH"]'::jsonb
      );
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.production_model_releases
      DROP CONSTRAINT ck_production_approved_quality_levels,
      DROP COLUMN approved_quality_levels;
    """)
