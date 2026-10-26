"""Allow business-sponsored shoppers to identify by email or mobile.

Revision ID: 20261026_0044
Revises: 20261025_0043
Created: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0044"
down_revision: str | None = "20261025_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "business_participants", sa.Column("normalized_email", sa.String(320), nullable=True)
    )
    op.alter_column("business_participants", "normalized_mobile", nullable=True)
    op.create_check_constraint(
        "ck_business_participants_one_identity",
        "business_participants",
        "(normalized_mobile IS NOT NULL) <> (normalized_email IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_business_participants_tenant_email",
        "business_participants",
        ["tenant_id", "normalized_email"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_business_participants_tenant_email", "business_participants", type_="unique"
    )
    op.drop_constraint(
        "ck_business_participants_one_identity", "business_participants", type_="check"
    )
    op.alter_column("business_participants", "normalized_mobile", nullable=False)
    op.drop_column("business_participants", "normalized_email")
