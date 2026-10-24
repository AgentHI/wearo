"""Add tenant-attributed shopper sessions and sponsored try-on usage.

Revision ID: 20261024_0031
Revises: 20261024_0030
Created: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0031"
down_revision: str | None = "20261024_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "business_participants": {
        "classification": "private",
        "owner_columns": ["business_account_id", "tenant_id"],
    },
    "business_sponsored_sessions": {
        "classification": "private",
        "owner_columns": ["business_account_id", "tenant_id"],
    },
    "business_sponsored_tryons": {
        "classification": "financial",
        "owner_columns": ["business_account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "business_participants",
        sa.Column(
            "participant_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("business_account_id", UUID, nullable=False),
        sa.Column("consumer_account_id", UUID, nullable=False),
        sa.Column("consumer_principal_id", UUID, nullable=False),
        sa.Column("normalized_mobile", sa.String(32), nullable=False),
        sa.Column("first_seen_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("latest_seen_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_business_participants_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["consumer_principal_id", "consumer_account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_business_participants_consumer",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "normalized_mobile", name="uq_business_participants_tenant_mobile"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "consumer_principal_id",
            name="uq_business_participants_tenant_principal",
        ),
    )
    op.create_index(
        "ix_business_participants_tenant_seen",
        "business_participants",
        ["tenant_id", "latest_seen_at"],
    )

    op.create_table(
        "business_sponsored_sessions",
        sa.Column(
            "session_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("participant_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("business_account_id", UUID, nullable=False),
        sa.Column("consumer_account_id", UUID, nullable=False),
        sa.Column("consumer_principal_id", UUID, nullable=False),
        sa.Column("allowance_limit", sa.Integer(), nullable=False),
        sa.Column("try_ons_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("allowance_limit >= 0", name="ck_sponsored_sessions_limit"),
        sa.CheckConstraint("try_ons_used >= 0", name="ck_sponsored_sessions_used"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'EXHAUSTED', 'EXPIRED')",
            name="ck_sponsored_sessions_status",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_sponsored_sessions_expiry"),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["business_participants.participant_id"],
            name="fk_sponsored_sessions_participant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_sponsored_sessions_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["consumer_principal_id", "consumer_account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_sponsored_sessions_consumer",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_sponsored_sessions_consumer_active",
        "business_sponsored_sessions",
        ["tenant_id", "consumer_principal_id", "expires_at"],
    )

    op.create_table(
        "business_sponsored_tryons",
        sa.Column("sponsored_tryon_id", UUID, primary_key=True),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("business_account_id", UUID, nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("usage_id", UUID, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["business_sponsored_sessions.session_id"],
            name="fk_sponsored_tryons_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usage_id"],
            ["billable_usage_records.usage_id"],
            name="fk_sponsored_tryons_usage",
        ),
        sa.UniqueConstraint(
            "business_account_id", "request_key", name="uq_sponsored_tryons_request"
        ),
        sa.UniqueConstraint("usage_id", name="uq_sponsored_tryons_usage"),
    )
    op.create_index(
        "ix_sponsored_tryons_tenant_time",
        "business_sponsored_tryons",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sponsored_tryons_tenant_time", table_name="business_sponsored_tryons")
    op.drop_table("business_sponsored_tryons")
    op.drop_index(
        "ix_sponsored_sessions_consumer_active", table_name="business_sponsored_sessions"
    )
    op.drop_table("business_sponsored_sessions")
    op.drop_index("ix_business_participants_tenant_seen", table_name="business_participants")
    op.drop_table("business_participants")
