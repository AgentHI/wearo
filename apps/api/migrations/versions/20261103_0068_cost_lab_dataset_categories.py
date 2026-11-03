"""Add category and custom prompt to dataset generation jobs.

Revision ID: 20261103_0068
Revises: 20261103_0067
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261103_0068"
down_revision: str | None = "20261103_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.dataset_generation_jobs
      ADD COLUMN category text NOT NULL DEFAULT 'ALL'
        CHECK (category IN ('ALL','PERSON','JEWELLERY','SAREE','DRESS')),
      ADD COLUMN custom_prompt text;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.dataset_generation_jobs
      DROP COLUMN custom_prompt,
      DROP COLUMN category;
    """)
