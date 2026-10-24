"""Track payment refunds and reconciliation discrepancies.

Revision ID: 20261023_0026
Revises: 20261023_0025
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0026"
down_revision: str | None = "20261023_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "payment_refunds": {"classification": "financial", "owner_columns": ["account_id"]},
    "payment_reconciliation_cases": {
        "classification": "financial",
        "owner_columns": ["account_id"],
    },
}
UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "invoices", sa.Column("status", sa.String(16), nullable=False, server_default="ISSUED")
    )
    op.create_check_constraint("ck_invoices_status", "invoices", "status IN ('ISSUED', 'VOIDED')")
    op.create_table(
        "payment_refunds",
        sa.Column("refund_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("payment_order_id", UUID, nullable=False),
        sa.Column("provider_refund_id", sa.String(120), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("tokens_reversed", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('RESOLVED', 'DISCREPANCY')", name="ck_payment_refunds_status"
        ),
        sa.ForeignKeyConstraint(
            ["payment_order_id", "account_id"],
            ["payment_orders.payment_order_id", "payment_orders.account_id"],
            name="fk_payment_refunds_order_account",
        ),
        sa.UniqueConstraint("payment_order_id", name="uq_payment_refunds_order"),
        sa.UniqueConstraint("provider_refund_id", name="uq_payment_refunds_provider"),
    )
    op.create_table(
        "payment_reconciliation_cases",
        sa.Column("case_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("payment_order_id", UUID, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", TIMESTAMP),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_payment_cases_status"),
        sa.ForeignKeyConstraint(
            ["payment_order_id", "account_id"],
            ["payment_orders.payment_order_id", "payment_orders.account_id"],
            name="fk_payment_cases_order_account",
        ),
    )


def downgrade() -> None:
    op.drop_table("payment_reconciliation_cases")
    op.drop_table("payment_refunds")
    op.drop_constraint("ck_invoices_status", "invoices", type_="check")
    op.drop_column("invoices", "status")
