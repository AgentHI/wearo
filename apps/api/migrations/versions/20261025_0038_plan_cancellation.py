"""Preserve plan history while preventing renewal after account cancellation.

Revision ID: 20261025_0038
Revises: 20261025_0037
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0038"
down_revision: str | None = "20261025_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "plan_assignments",
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("plan_assignments", "cancelled_at")
