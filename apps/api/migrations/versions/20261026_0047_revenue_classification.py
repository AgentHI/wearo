"""Classify platform payment revenue.

Revision ID: 20261026_0047
Revises: 20261026_0046
Created: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0047"
down_revision: str | None = "20261026_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "payment_orders",
        sa.Column(
            "revenue_type",
            sa.String(24),
            nullable=False,
            server_default="TOKEN_PURCHASE",
        ),
    )
    op.create_check_constraint(
        "ck_payment_orders_revenue_type",
        "payment_orders",
        "revenue_type IN ('SUBSCRIPTION', 'TOKEN_PURCHASE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_payment_orders_revenue_type", "payment_orders", type_="check")
    op.drop_column("payment_orders", "revenue_type")
