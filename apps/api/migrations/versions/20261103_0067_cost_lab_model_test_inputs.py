"""Store input image paths for successful Cost Lab model tests.

Revision ID: 20261103_0067
Revises: 20261103_0066
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261103_0067"
down_revision: str | None = "20261103_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.ai_models
      ADD COLUMN test_input_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
      ADD CONSTRAINT ck_ai_models_test_input_paths
        CHECK (jsonb_typeof(test_input_paths) = 'array');
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.ai_models
      DROP CONSTRAINT ck_ai_models_test_input_paths,
      DROP COLUMN test_input_paths;
    """)
