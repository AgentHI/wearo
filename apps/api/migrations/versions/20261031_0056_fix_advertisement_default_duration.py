"""Correct legacy advertisement end-date backfill.

Revision ID: 20261031_0056
Revises: 20261031_0055
Created: 2026-10-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261031_0056"
down_revision: str | None = "20261031_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""UPDATE store_advertisements
        SET ends_on=starts_on
        WHERE ends_on='9999-12-31'::date""")


def downgrade() -> None:
    # The previous open-ended value cannot be distinguished after correction.
    pass
