"""Split benchmark input and output image quality.

Revision ID: 20261102_0065
Revises: 20261102_0064
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261102_0065"
down_revision: str | None = "20261102_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.benchmark_combinations
      ADD COLUMN output_quality text NOT NULL DEFAULT 'HIGH'
        CHECK (output_quality IN ('LOW','MEDIUM','HIGH'));
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.benchmark_combinations DROP COLUMN output_quality;
    """)
