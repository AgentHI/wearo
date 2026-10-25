"""Record successful account deletion completion.

Revision ID: 20261025_0041
Revises: 20261025_0040
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0041"
down_revision: str | None = "20261025_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column("accounts", sa.Column("deletion_outcome", sa.String(24)))
    op.execute(
        "UPDATE accounts SET deletion_outcome = 'COMPLETED' WHERE status = 'PERMANENTLY_DELETED'"
    )
    op.drop_constraint("ck_accounts_deletion_lifecycle", "accounts", type_="check")
    op.create_check_constraint(
        "ck_accounts_deletion_lifecycle",
        "accounts",
        "(status = 'DELETION_PENDING' AND cancellation_at IS NOT NULL "
        "AND deletion_at = cancellation_at + INTERVAL '30 days' "
        "AND permanently_deleted_at IS NULL AND deletion_outcome IS NULL) OR "
        "(status = 'PERMANENTLY_DELETED' AND cancellation_at IS NOT NULL "
        "AND deletion_at = cancellation_at + INTERVAL '30 days' "
        "AND permanently_deleted_at >= deletion_at "
        "AND deletion_outcome = 'COMPLETED') OR "
        "(status NOT IN ('DELETION_PENDING', 'PERMANENTLY_DELETED') "
        "AND cancellation_at IS NULL AND deletion_at IS NULL "
        "AND permanently_deleted_at IS NULL AND deletion_outcome IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_accounts_deletion_lifecycle", "accounts", type_="check")
    op.drop_column("accounts", "deletion_outcome")
    op.create_check_constraint(
        "ck_accounts_deletion_lifecycle",
        "accounts",
        "(status = 'DELETION_PENDING' AND cancellation_at IS NOT NULL "
        "AND deletion_at = cancellation_at + INTERVAL '30 days' "
        "AND permanently_deleted_at IS NULL) OR "
        "(status = 'PERMANENTLY_DELETED' AND cancellation_at IS NOT NULL "
        "AND deletion_at = cancellation_at + INTERVAL '30 days' "
        "AND permanently_deleted_at >= deletion_at) OR "
        "(status NOT IN ('DELETION_PENDING', 'PERMANENTLY_DELETED') "
        "AND cancellation_at IS NULL AND deletion_at IS NULL "
        "AND permanently_deleted_at IS NULL)",
    )
