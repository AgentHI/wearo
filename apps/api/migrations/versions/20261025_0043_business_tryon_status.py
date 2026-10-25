"""Add the business try-on lifecycle state.

Revision ID: 20261025_0043
Revises: 20261025_0042
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0043"
down_revision: str | None = "20261025_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "business_tenants",
        sa.Column("try_on_status", sa.String(16), nullable=False, server_default="ACTIVE"),
    )
    op.create_check_constraint(
        "ck_business_tenants_try_on_status",
        "business_tenants",
        "try_on_status IN ('ACTIVE', 'PAUSED', 'CANCELLED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_business_tenants_try_on_status", "business_tenants", type_="check")
    op.drop_column("business_tenants", "try_on_status")
