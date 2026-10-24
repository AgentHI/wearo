"""Record business invoice preference explicitly.

Revision ID: 20261023_0020
Revises: 20261023_0019
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0020"
down_revision: str | None = "20261023_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "business_profiles",
        sa.Column("tax_invoice_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("business_profiles", "tax_invoice_requested")
