"""Constrain production model routing priority to the 1-20 scale.

Revision ID: 20261104_0080
Revises: 20261104_0079
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0080"
down_revision: str | None = "20261104_0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.production_model_releases
      DROP CONSTRAINT production_model_priority_positive;
    ALTER TABLE cost_lab.production_model_releases
      ADD CONSTRAINT production_model_priority_range
      CHECK (priority IS NULL OR priority BETWEEN 1 AND 20);
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.production_model_releases
      DROP CONSTRAINT production_model_priority_range;
    ALTER TABLE cost_lab.production_model_releases
      ADD CONSTRAINT production_model_priority_positive
      CHECK (priority IS NULL OR priority > 0);
    """)
