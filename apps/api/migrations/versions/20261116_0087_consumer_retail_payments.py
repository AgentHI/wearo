"""Allow payment orders for consumer retail packages.

Revision ID: 20261116_0087
Revises: 20261115_0086
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261116_0087"
down_revision: str | None = "20261115_0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("payment_orders", "pack_id", existing_type=postgresql.UUID(), nullable=True)
    op.add_column(
        "payment_orders",
        sa.Column("retail_package_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_payment_orders_retail_package",
        "payment_orders",
        "retail_tryon_packages",
        ["retail_package_id"],
        ["retail_package_id"],
    )
    op.create_check_constraint(
        "ck_payment_orders_one_package",
        "payment_orders",
        "(pack_id IS NOT NULL) <> (retail_package_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_payment_orders_one_package", "payment_orders", type_="check")
    op.drop_constraint("fk_payment_orders_retail_package", "payment_orders", type_="foreignkey")
    op.drop_column("payment_orders", "retail_package_id")
    op.alter_column("payment_orders", "pack_id", existing_type=postgresql.UUID(), nullable=False)
