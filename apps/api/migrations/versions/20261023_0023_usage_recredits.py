"""Add immutable automatic usage recredits.

Revision ID: 20261023_0023
Revises: 20261023_0022
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0023"
down_revision: str | None = "20261023_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "usage_recredits": {
        "classification": "financial",
        "owner_columns": ["account_id", "tenant_id"],
    },
}
UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_billable_usage_id_account", "billable_usage_records", ["usage_id", "account_id"]
    )
    op.create_table(
        "usage_recredits",
        sa.Column(
            "recredit_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("usage_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("token_amount", sa.BigInteger(), nullable=False),
        sa.Column("ledger_entry_id", UUID, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "reason_code IN ('FAILED', 'CANCELLED_BEFORE_PROCESSING', 'NON_DELIVERED')",
            name="ck_usage_recredits_reason",
        ),
        sa.CheckConstraint("token_amount > 0", name="ck_usage_recredits_amount"),
        sa.ForeignKeyConstraint(
            ["usage_id", "account_id"],
            ["billable_usage_records.usage_id", "billable_usage_records.account_id"],
            name="fk_usage_recredits_usage_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_usage_recredits_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_entry_id", "account_id"],
            ["ledger_entries.entry_id", "ledger_entries.account_id"],
            name="fk_usage_recredits_ledger_account",
        ),
        sa.UniqueConstraint("usage_id", name="uq_usage_recredits_usage"),
        sa.UniqueConstraint("ledger_entry_id", name="uq_usage_recredits_ledger"),
    )
    op.execute(
        """CREATE FUNCTION reject_usage_recredit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'usage recredits are append-only';
        END; $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_usage_recredits_append_only
        BEFORE UPDATE OR DELETE ON usage_recredits
        FOR EACH ROW EXECUTE FUNCTION reject_usage_recredit_mutation()"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_usage_recredits_append_only ON usage_recredits")
    op.execute("DROP FUNCTION reject_usage_recredit_mutation()")
    op.drop_table("usage_recredits")
    op.drop_constraint("uq_billable_usage_id_account", "billable_usage_records", type_="unique")
