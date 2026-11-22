"""Add monotonic person presentation classification.

Revision ID: 20261122_0091
Revises: 20261122_0090
Created: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0091"
down_revision: str | None = "20261122_0090"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def _add_person_category(table: str) -> None:
    op.add_column(
        table,
        sa.Column("person_category", sa.String(16), nullable=False, server_default="unknown"),
    )
    op.create_check_constraint(
        f"ck_{table}_person_category",
        table,
        "person_category IN ('unknown','girl','woman')",
    )


def upgrade() -> None:
    # Per-attempt evidence belongs on the quote/result. A login may represent several people,
    # so the durable person classification is stored in account_persons by revision 0094.
    for table in ("render_quotes", "render_results"):
        _add_person_category(table)


def downgrade() -> None:
    for table in ("render_results", "render_quotes"):
        op.drop_constraint(f"ck_{table}_person_category", table, type_="check")
        op.drop_column(table, "person_category")
