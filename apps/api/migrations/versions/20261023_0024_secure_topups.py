"""Add tenant-bound top-up snapshots and immutable payment receipts.

Revision ID: 20261023_0024
Revises: 20261023_0023
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0024"
down_revision: str | None = "20261023_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "payment_receipts": {"classification": "financial", "owner_columns": ["account_id"]},
}
UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("payment_orders", sa.Column("tenant_id", UUID))
    op.add_column("payment_orders", sa.Column("purchased_tokens", sa.BigInteger()))
    op.add_column("payment_orders", sa.Column("promo_tokens", sa.BigInteger()))
    op.add_column("payment_orders", sa.Column("checkout_url", sa.String(1000)))
    op.create_foreign_key(
        "fk_payment_orders_tenant_account",
        "payment_orders",
        "business_tenants",
        ["tenant_id", "account_id"],
        ["tenant_id", "account_id"],
    )
    op.create_table(
        "payment_receipts",
        sa.Column(
            "receipt_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("payment_order_id", UUID, nullable=False),
        sa.Column("receipt_number", sa.String(80), nullable=False),
        sa.Column("provider_payment_id", sa.String(120), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("tokens_credited", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_minor > 0", name="ck_payment_receipts_amount"),
        sa.CheckConstraint("tokens_credited > 0", name="ck_payment_receipts_tokens"),
        sa.ForeignKeyConstraint(
            ["payment_order_id", "account_id"],
            ["payment_orders.payment_order_id", "payment_orders.account_id"],
            name="fk_payment_receipts_order_account",
        ),
        sa.UniqueConstraint("payment_order_id", name="uq_payment_receipts_order"),
        sa.UniqueConstraint("receipt_number", name="uq_payment_receipts_number"),
        sa.UniqueConstraint("provider_payment_id", name="uq_payment_receipts_provider_payment"),
    )
    op.execute(
        """CREATE TRIGGER trg_payment_receipts_append_only BEFORE UPDATE OR DELETE
        ON payment_receipts FOR EACH ROW EXECUTE FUNCTION reject_ledger_mutation()"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_payment_receipts_append_only ON payment_receipts")
    op.drop_table("payment_receipts")
    op.drop_constraint("fk_payment_orders_tenant_account", "payment_orders", type_="foreignkey")
    op.drop_column("payment_orders", "promo_tokens")
    op.drop_column("payment_orders", "purchased_tokens")
    op.drop_column("payment_orders", "checkout_url")
    op.drop_column("payment_orders", "tenant_id")
