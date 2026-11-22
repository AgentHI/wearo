"""Add approximate single-number person age estimates.

Revision ID: 20261122_0093
Revises: 20261122_0092
Created: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0093"
down_revision: str | None = "20261122_0092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def _add_estimated_age(table: str) -> None:
    op.add_column(table, sa.Column("estimated_age", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        f"ck_{table}_estimated_age",
        table,
        "estimated_age IS NULL OR estimated_age BETWEEN 1 AND 120",
    )


def upgrade() -> None:
    for table in ("render_quotes", "render_results"):
        _add_estimated_age(table)


def downgrade() -> None:
    for table in ("render_results", "render_quotes"):
        op.drop_constraint(f"ck_{table}_estimated_age", table, type_="check")
        op.drop_column(table, "estimated_age")
