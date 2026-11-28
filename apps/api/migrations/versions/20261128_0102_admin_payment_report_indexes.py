"""Index B2C and B2B payment reporting periods.

Revision ID: 20261128_0102
Revises: 20261128_0101
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261128_0102"
down_revision: str | None = "20261128_0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.create_index(
        "ix_payment_orders_b2c_report_time",
        "payment_orders",
        ["created_at"],
        postgresql_where=sa.text("tenant_id IS NULL AND retail_package_id IS NOT NULL"),
    )
    op.create_index(
        "ix_payment_orders_b2b_report_time",
        "payment_orders",
        ["created_at"],
        postgresql_where=sa.text("tenant_id IS NOT NULL AND pack_id IS NOT NULL"),
    )
    op.create_index(
        "ix_payment_receipts_report_time",
        "payment_receipts",
        ["issued_at"],
    )
    op.create_index(
        "ix_payment_refunds_report_time",
        "payment_refunds",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_refunds_report_time", table_name="payment_refunds")
    op.drop_index("ix_payment_receipts_report_time", table_name="payment_receipts")
    op.drop_index("ix_payment_orders_b2b_report_time", table_name="payment_orders")
    op.drop_index("ix_payment_orders_b2c_report_time", table_name="payment_orders")
