"""Persist retryable account deletion attempts.

Revision ID: 20261025_0042
Revises: 20261025_0041
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261025_0042"
down_revision: str | None = "20261025_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "account_deletion_attempts": {"classification": "audit", "owner_columns": ["account_id"]}
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "account_deletion_attempts",
        sa.Column("attempt_id", UUID, primary_key=True),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_code", sa.String(32)),
        sa.Column("started_at", TIMESTAMP, nullable=False),
        sa.Column("completed_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'FAILED', 'SKIPPED', 'COMPLETED')",
            name="ck_account_deletion_attempts_status",
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'COMPLETED' AND completed_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status IN ('FAILED', 'SKIPPED') AND completed_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_account_deletion_attempts_completion",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_account_deletion_attempts_account",
        ),
    )
    op.create_index(
        "ix_account_deletion_attempts_account_time",
        "account_deletion_attempts",
        ["account_id", "started_at"],
    )
    op.create_index(
        "ix_account_deletion_attempts_running",
        "account_deletion_attempts",
        ["status", "started_at"],
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index("ix_account_deletion_attempts_running", table_name="account_deletion_attempts")
    op.drop_index(
        "ix_account_deletion_attempts_account_time", table_name="account_deletion_attempts"
    )
    op.drop_table("account_deletion_attempts")
