"""Add direction and quality controls to Cost Lab dataset generation.

Revision ID: 20261102_0064
Revises: 20261102_0063
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261102_0064"
down_revision: str | None = "20261102_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.dataset_generation_jobs
      ADD COLUMN generation_quality text NOT NULL DEFAULT 'HIGH'
        CHECK (generation_quality IN ('LOW','MEDIUM','HIGH')),
      ADD COLUMN direction text;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.dataset_generation_jobs
      DROP COLUMN direction,
      DROP COLUMN generation_quality;
    """)
