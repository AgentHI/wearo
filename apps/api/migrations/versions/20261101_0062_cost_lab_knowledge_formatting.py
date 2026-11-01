"""Add LLM-formatted Cost Lab knowledge.

Revision ID: 20261101_0062
Revises: 20261101_0061
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261101_0062"
down_revision: str | None = "20261101_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.knowledge_items
      ADD COLUMN formatted_html text,
      ADD COLUMN formatter_model text,
      ADD COLUMN formatting_usage jsonb NOT NULL DEFAULT '{}';
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.knowledge_items
      DROP COLUMN formatting_usage,
      DROP COLUMN formatter_model,
      DROP COLUMN formatted_html;
    """)
