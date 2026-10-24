"""Enforce one consumer or tenant paying context for billable records.

Revision ID: 20261023_0021
Revises: 20261023_0020
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0021"
down_revision: str | None = "20261023_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("ledger_entries", sa.Column("tenant_id", UUID))
    op.execute("ALTER TABLE ledger_entries DISABLE TRIGGER trg_ledger_entries_append_only")
    op.execute(
        """
        UPDATE ledger_entries entry SET tenant_id = tenant.tenant_id
        FROM business_tenants tenant
        WHERE tenant.account_id = entry.account_id
        """
    )
    op.execute("ALTER TABLE ledger_entries ENABLE TRIGGER trg_ledger_entries_append_only")
    op.create_foreign_key(
        "fk_ledger_entries_tenant_account",
        "ledger_entries",
        "business_tenants",
        ["tenant_id", "account_id"],
        ["tenant_id", "account_id"],
    )
    op.create_index("ix_ledger_entries_tenant_time", "ledger_entries", ["tenant_id", "created_at"])
    op.execute(
        """
        CREATE FUNCTION enforce_single_paying_context() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE account_kind text;
        BEGIN
            SELECT kind INTO account_kind FROM accounts WHERE account_id = NEW.account_id;
            IF account_kind = 'CONSUMER' AND NEW.tenant_id IS NOT NULL THEN
                RAISE EXCEPTION 'consumer payer cannot have a tenant context';
            END IF;
            IF account_kind = 'TENANT' AND NEW.tenant_id IS NULL THEN
                RAISE EXCEPTION 'business payer requires a tenant context';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in (
        "render_quotes",
        "render_jobs",
        "render_attempts",
        "render_results",
        "ledger_entries",
    ):
        op.execute(
            f"""CREATE TRIGGER trg_{table}_paying_context
            BEFORE INSERT OR UPDATE OF account_id, tenant_id ON {table}
            FOR EACH ROW EXECUTE FUNCTION enforce_single_paying_context()"""
        )


def downgrade() -> None:
    for table in (
        "ledger_entries",
        "render_results",
        "render_attempts",
        "render_jobs",
        "render_quotes",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_paying_context ON {table}")
    op.execute("DROP FUNCTION enforce_single_paying_context()")
    op.drop_index("ix_ledger_entries_tenant_time", table_name="ledger_entries")
    op.drop_constraint("fk_ledger_entries_tenant_account", "ledger_entries", type_="foreignkey")
    op.drop_column("ledger_entries", "tenant_id")
