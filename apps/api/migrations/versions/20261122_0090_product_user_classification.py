"""Add monotonic product-based consumer classification.

Revision ID: 20261122_0090
Revises: 20261121_0089
Created: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261122_0090"
down_revision: str | None = "20261121_0089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "product_category",
            sa.String(16),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.create_check_constraint(
        "ck_accounts_product_category",
        "accounts",
        "product_category IN ('unknown','basic','premium','luxury','ultra_luxury')",
    )

    for table in ("render_quotes", "render_results"):
        op.add_column(table, sa.Column("product_kind", sa.String(16)))
        op.add_column(
            table,
            sa.Column(
                "product_category",
                sa.String(16),
                nullable=False,
                server_default="unknown",
            ),
        )
        op.add_column(table, sa.Column("classification_evidence", postgresql.JSONB()))
        op.create_check_constraint(
            f"ck_{table}_product_kind",
            table,
            "product_kind IS NULL OR product_kind IN ('APPAREL','JEWELLERY')",
        )
        op.create_check_constraint(
            f"ck_{table}_product_category",
            table,
            "product_category IN ('unknown','basic','premium','luxury','ultra_luxury')",
        )


def downgrade() -> None:
    for table in ("render_results", "render_quotes"):
        op.drop_constraint(f"ck_{table}_product_category", table, type_="check")
        op.drop_constraint(f"ck_{table}_product_kind", table, type_="check")
        op.drop_column(table, "classification_evidence")
        op.drop_column(table, "product_category")
        op.drop_column(table, "product_kind")
    op.drop_constraint("ck_accounts_product_category", "accounts", type_="check")
    op.drop_column("accounts", "product_category")
