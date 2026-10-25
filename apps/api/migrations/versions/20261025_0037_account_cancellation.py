"""Add the account cancellation and permanent deletion lifecycle.

Revision ID: 20261025_0037
Revises: 20261024_0036
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0037"
down_revision: str | None = "20261024_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.drop_constraint("ck_accounts_status", "accounts", type_="check")
    op.alter_column(
        "accounts",
        "status",
        existing_type=sa.String(16),
        type_=sa.String(24),
        existing_nullable=False,
        existing_server_default="ACTIVE",
    )
    op.add_column("accounts", sa.Column("cancellation_at", TIMESTAMP))
    op.add_column("accounts", sa.Column("deletion_at", TIMESTAMP))
    op.add_column("accounts", sa.Column("permanently_deleted_at", TIMESTAMP))
    op.create_check_constraint(
        "ck_accounts_status",
        "accounts",
        "status IN ('ACTIVE', 'SUSPENDED', 'CLOSED', 'DELETION_PENDING', 'PERMANENTLY_DELETED')",
    )
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
    op.create_index("ix_accounts_deletion_due", "accounts", ["status", "deletion_at"])


def downgrade() -> None:
    op.drop_index("ix_accounts_deletion_due", table_name="accounts")
    op.drop_constraint("ck_accounts_deletion_lifecycle", "accounts", type_="check")
    op.drop_constraint("ck_accounts_status", "accounts", type_="check")
    op.drop_column("accounts", "permanently_deleted_at")
    op.drop_column("accounts", "deletion_at")
    op.drop_column("accounts", "cancellation_at")
    op.execute(
        "UPDATE accounts SET status = 'CLOSED' WHERE status IN "
        "('DELETION_PENDING', 'PERMANENTLY_DELETED')"
    )
    op.alter_column(
        "accounts",
        "status",
        existing_type=sa.String(24),
        type_=sa.String(16),
        existing_nullable=False,
        existing_server_default="ACTIVE",
    )
    op.create_check_constraint(
        "ck_accounts_status",
        "accounts",
        "status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')",
    )
