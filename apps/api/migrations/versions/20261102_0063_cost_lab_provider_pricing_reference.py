"""Add provider pricing references to Cost Lab.

Revision ID: 20261102_0063
Revises: 20261101_0062
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261102_0063"
down_revision: str | None = "20261101_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.model_providers
      ADD COLUMN pricing_reference_url text,
      ADD COLUMN pricing_reference_text text;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.model_providers
      DROP COLUMN pricing_reference_text,
      DROP COLUMN pricing_reference_url;
    """)
