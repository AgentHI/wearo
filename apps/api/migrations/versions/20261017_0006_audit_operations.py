"""Add immutable audit evidence and operations cases.

Revision ID: 20261017_0006
Revises: 20261017_0005
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0006"
down_revision: str | None = "20261017_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "audit_events": {"classification": "audit", "owner_columns": ["account_id", "tenant_id"]},
    "operation_cases": {
        "classification": "audit",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "operation_case_events": {
        "classification": "audit",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column(
            "audit_event_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID),
        sa.Column("tenant_id", UUID),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("actor_id", UUID),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", UUID),
        sa.Column("reason", sa.Text()),
        sa.Column("request_id", UUID),
        sa.Column("before_summary", postgresql.JSONB()),
        sa.Column("after_summary", postgresql.JSONB()),
        sa.Column("occurred_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "actor_type IN ('PRINCIPAL', 'ADMIN', 'SERVICE', 'SYSTEM')",
            name="ck_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "actor_type = 'SYSTEM' OR actor_id IS NOT NULL", name="ck_audit_events_actor_id"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_audit_events_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_audit_events_tenant_account",
        ),
    )
    op.create_index(
        "ix_audit_events_scope_time", "audit_events", ["account_id", "tenant_id", "occurred_at"]
    )
    op.execute(
        """CREATE FUNCTION reject_audit_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'audit events are immutable'; END; $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()"""
    )

    op.create_table(
        "operation_cases",
        sa.Column("case_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID),
        sa.Column("tenant_id", UUID),
        sa.Column("case_type", sa.String(24), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="SUBMITTED"),
        sa.Column("opened_by_type", sa.String(24), nullable=False),
        sa.Column("opened_by_id", UUID),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("disposition", sa.Text()),
        sa.Column("resolved_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "case_type IN ('SUPPORT', 'DATA_REQUEST', 'PAYMENT', 'QUALITY', 'ANOMALY')",
            name="ck_operation_cases_type",
        ),
        sa.CheckConstraint(
            "state IN ('SUBMITTED', 'OPEN', 'IN_PROGRESS', 'RESOLVED', 'REJECTED')",
            name="ck_operation_cases_state",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_operation_cases_reason"),
        sa.CheckConstraint(
            "(state IN ('RESOLVED', 'REJECTED') AND resolved_at IS NOT NULL "
            "AND disposition IS NOT NULL) OR "
            "(state NOT IN ('RESOLVED', 'REJECTED') AND resolved_at IS NULL)",
            name="ck_operation_cases_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_operation_cases_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_operation_cases_tenant_account",
        ),
        sa.UniqueConstraint("case_id", "account_id", name="uq_operation_cases_id_account"),
    )
    op.create_index(
        "ix_operation_cases_scope_state",
        "operation_cases",
        ["account_id", "tenant_id", "state", "created_at"],
    )

    op.create_table(
        "operation_case_events",
        sa.Column(
            "case_event_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("account_id", UUID),
        sa.Column("tenant_id", UUID),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("actor_id", UUID),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("from_state", sa.String(24)),
        sa.Column("to_state", sa.String(24), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_operation_case_events_reason"),
        sa.ForeignKeyConstraint(
            ["case_id", "account_id"],
            ["operation_cases.case_id", "operation_cases.account_id"],
            name="fk_operation_case_events_case_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_operation_case_events_tenant_account",
        ),
    )
    op.create_index(
        "ix_operation_case_events_case_time",
        "operation_case_events",
        ["case_id", "created_at"],
    )
    op.execute(
        """CREATE FUNCTION reject_case_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'case events are immutable'; END; $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_case_events_immutable BEFORE UPDATE OR DELETE ON operation_case_events
        FOR EACH ROW EXECUTE FUNCTION reject_case_event_mutation()"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_case_events_immutable ON operation_case_events")
    op.execute("DROP FUNCTION reject_case_event_mutation()")
    op.drop_index("ix_operation_case_events_case_time", table_name="operation_case_events")
    op.drop_table("operation_case_events")
    op.drop_index("ix_operation_cases_scope_state", table_name="operation_cases")
    op.drop_table("operation_cases")
    op.execute("DROP TRIGGER trg_audit_events_immutable ON audit_events")
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
    op.drop_index("ix_audit_events_scope_time", table_name="audit_events")
    op.drop_table("audit_events")
