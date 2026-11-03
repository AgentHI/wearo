"""Track Cost Lab model test status and generated previews.

Revision ID: 20261103_0066
Revises: 20261102_0065
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261103_0066"
down_revision: str | None = "20261102_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.ai_models
      ADD COLUMN tested_at timestamptz,
      ADD COLUMN tested_method text CHECK (tested_method IN ('GENERATED','MANUAL')),
      ADD COLUMN test_prompt text,
      ADD COLUMN test_output_path text,
      ADD COLUMN test_provider_request_id text;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.ai_models
      DROP COLUMN test_provider_request_id,
      DROP COLUMN test_output_path,
      DROP COLUMN test_prompt,
      DROP COLUMN tested_method,
      DROP COLUMN tested_at;
    """)
