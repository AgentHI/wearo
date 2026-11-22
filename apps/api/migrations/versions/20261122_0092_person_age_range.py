"""Add approximate person age ranges.

Revision ID: 20261122_0092
Revises: 20261122_0091
Created: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0092"
down_revision: str | None = "20261122_0091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}

AGE_RANGE_VALUES = "'unknown','under_10','10_19','20_29','30_39','40_49','50_59','60_plus'"


def _add_age_range(table: str) -> None:
    op.add_column(
        table,
        sa.Column("age_range", sa.String(16), nullable=False, server_default="unknown"),
    )
    op.create_check_constraint(
        f"ck_{table}_age_range",
        table,
        f"age_range IN ({AGE_RANGE_VALUES})",
    )


def upgrade() -> None:
    for table in ("render_quotes", "render_results"):
        _add_age_range(table)


def downgrade() -> None:
    for table in ("render_results", "render_quotes"):
        op.drop_constraint(f"ck_{table}_age_range", table, type_="check")
        op.drop_column(table, "age_range")
