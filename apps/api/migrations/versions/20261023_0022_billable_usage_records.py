"""Add itemized exactly-once billable usage records.

Revision ID: 20261023_0022
Revises: 20261023_0021
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0022"
down_revision: str | None = "20261023_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "billable_usage_records": {
        "classification": "financial",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "billable_usage_records",
        sa.Column("usage_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("action_code", sa.String(40), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("price_version_id", UUID, nullable=False),
        sa.Column("token_cost", sa.BigInteger(), nullable=False),
        sa.Column("ledger_entry_id", UUID, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("token_cost > 0", name="ck_billable_usage_records_cost"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_billable_usage_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_billable_usage_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_billable_usage_principal_account",
        ),
        sa.ForeignKeyConstraint(
            ["price_version_id"],
            ["price_versions.price_version_id"],
            name="fk_billable_usage_price",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_entry_id", "account_id"],
            ["ledger_entries.entry_id", "ledger_entries.account_id"],
            name="fk_billable_usage_ledger_account",
        ),
        sa.UniqueConstraint("account_id", "request_key", name="uq_billable_usage_account_request"),
        sa.UniqueConstraint("ledger_entry_id", name="uq_billable_usage_ledger"),
    )
    op.create_index(
        "ix_billable_usage_tenant_time",
        "billable_usage_records",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_billable_usage_tenant_time", table_name="billable_usage_records")
    op.drop_table("billable_usage_records")
