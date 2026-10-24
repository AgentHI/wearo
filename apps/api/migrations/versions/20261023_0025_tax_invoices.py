"""Add tax calculation snapshots to top-ups and invoices.

Revision ID: 20261023_0025
Revises: 20261023_0024
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0025"
down_revision: str | None = "20261023_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "token_packs",
        sa.Column("tax_rate_basis_points", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_token_packs_tax_rate", "token_packs", "tax_rate_basis_points BETWEEN 0 AND 10000"
    )
    op.add_column("payment_orders", sa.Column("tax_rate_basis_points", sa.Integer()))
    op.add_column("invoices", sa.Column("tenant_id", UUID))
    op.add_column("invoices", sa.Column("subtotal_minor", sa.BigInteger()))
    op.add_column("invoices", sa.Column("tax_minor", sa.BigInteger()))
    op.create_foreign_key(
        "fk_invoices_tenant_account",
        "invoices",
        "business_tenants",
        ["tenant_id", "account_id"],
        ["tenant_id", "account_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_invoices_tenant_account", "invoices", type_="foreignkey")
    op.drop_column("invoices", "tax_minor")
    op.drop_column("invoices", "subtotal_minor")
    op.drop_column("invoices", "tenant_id")
    op.drop_column("payment_orders", "tax_rate_basis_points")
    op.drop_constraint("ck_token_packs_tax_rate", "token_packs", type_="check")
    op.drop_column("token_packs", "tax_rate_basis_points")
