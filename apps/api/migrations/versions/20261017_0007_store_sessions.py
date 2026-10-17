"""Add temporary store sessions, exact-item enquiries, and tenant events.

Revision ID: 20261017_0007
Revises: 20261017_0006
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0007"
down_revision: str | None = "20261017_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "guest_store_sessions": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "store_session_media": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "enquiries": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "tenant_aggregate_events": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_tenant_memberships_id_tenant_account",
        "tenant_memberships",
        ["membership_id", "tenant_id", "account_id"],
    )
    op.create_unique_constraint(
        "uq_catalog_items_id_tenant_account",
        "catalog_items",
        ["item_id", "tenant_id", "account_id"],
    )

    op.create_table(
        "guest_store_sessions",
        sa.Column(
            "store_session_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("membership_id", UUID, nullable=False),
        sa.Column("consent_id", UUID),
        sa.Column("state", sa.String(16), nullable=False, server_default="CREATED"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("finished_at", TIMESTAMP),
        sa.Column("revoked_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "state IN ('CREATED', 'ACTIVE', 'FINISHED', 'EXPIRED')",
            name="ck_guest_store_sessions_state",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_guest_store_sessions_expiry"),
        sa.CheckConstraint(
            "(state = 'FINISHED' AND finished_at IS NOT NULL AND revoked_at IS NOT NULL) OR "
            "(state = 'EXPIRED' AND revoked_at IS NOT NULL) OR "
            "(state IN ('CREATED', 'ACTIVE') AND finished_at IS NULL AND revoked_at IS NULL)",
            name="ck_guest_store_sessions_terminal_state",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id", "tenant_id", "account_id"],
            [
                "tenant_memberships.membership_id",
                "tenant_memberships.tenant_id",
                "tenant_memberships.account_id",
            ],
            name="fk_guest_store_sessions_membership_scope",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_guest_store_sessions_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["consent_id"], ["consent_records.consent_id"], name="fk_guest_store_sessions_consent"
        ),
        sa.UniqueConstraint(
            "store_session_id", "tenant_id", "account_id", name="uq_guest_store_sessions_scope"
        ),
    )
    op.create_index(
        "ix_guest_store_sessions_tenant_state",
        "guest_store_sessions",
        ["tenant_id", "state", "expires_at"],
    )

    op.create_table(
        "store_session_media",
        sa.Column(
            "session_media_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("store_session_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("asset_id", UUID, nullable=False),
        sa.Column("media_role", sa.String(24), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "media_role IN ('PERSON_SOURCE', 'RENDER_RESULT')", name="ck_store_session_media_role"
        ),
        sa.ForeignKeyConstraint(
            ["store_session_id", "tenant_id", "account_id"],
            [
                "guest_store_sessions.store_session_id",
                "guest_store_sessions.tenant_id",
                "guest_store_sessions.account_id",
            ],
            name="fk_store_session_media_session_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_store_session_media_asset_account",
        ),
        sa.UniqueConstraint("store_session_id", "asset_id", name="uq_store_session_media_asset"),
    )

    op.create_table(
        "enquiries",
        sa.Column(
            "enquiry_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("store_session_id", UUID, nullable=False),
        sa.Column("catalog_item_id", UUID, nullable=False),
        sa.Column("contact_channel", sa.String(16), nullable=False),
        sa.Column("contact_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("contact_consent_at", TIMESTAMP, nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="SUBMITTED"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("contact_channel IN ('PHONE', 'EMAIL')", name="ck_enquiries_channel"),
        sa.CheckConstraint(
            "state IN ('SUBMITTED', 'CONTACTED', 'CLOSED')", name="ck_enquiries_state"
        ),
        sa.ForeignKeyConstraint(
            ["store_session_id", "tenant_id", "account_id"],
            [
                "guest_store_sessions.store_session_id",
                "guest_store_sessions.tenant_id",
                "guest_store_sessions.account_id",
            ],
            name="fk_enquiries_session_scope",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_item_id", "tenant_id", "account_id"],
            ["catalog_items.item_id", "catalog_items.tenant_id", "catalog_items.account_id"],
            name="fk_enquiries_item_scope",
        ),
    )
    op.create_index("ix_enquiries_tenant_time", "enquiries", ["tenant_id", "created_at"])

    op.create_table(
        "tenant_aggregate_events",
        sa.Column(
            "aggregate_event_id",
            UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("store_session_id", UUID),
        sa.Column("catalog_item_id", UUID),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "event_type IN ('SESSION_STARTED', 'RENDER_SUCCEEDED', "
            "'ITEM_SELECTED', 'ENQUIRY_CREATED')",
            name="ck_tenant_aggregate_events_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_tenant_aggregate_events_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["store_session_id", "tenant_id", "account_id"],
            [
                "guest_store_sessions.store_session_id",
                "guest_store_sessions.tenant_id",
                "guest_store_sessions.account_id",
            ],
            name="fk_tenant_aggregate_events_session_scope",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_item_id", "tenant_id", "account_id"],
            ["catalog_items.item_id", "catalog_items.tenant_id", "catalog_items.account_id"],
            name="fk_tenant_aggregate_events_item_scope",
        ),
    )
    op.create_index(
        "ix_tenant_aggregate_events_rollup",
        "tenant_aggregate_events",
        ["tenant_id", "event_type", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_aggregate_events_rollup", table_name="tenant_aggregate_events")
    op.drop_table("tenant_aggregate_events")
    op.drop_index("ix_enquiries_tenant_time", table_name="enquiries")
    op.drop_table("enquiries")
    op.drop_table("store_session_media")
    op.drop_index("ix_guest_store_sessions_tenant_state", table_name="guest_store_sessions")
    op.drop_table("guest_store_sessions")
    op.drop_constraint("uq_catalog_items_id_tenant_account", "catalog_items", type_="unique")
    op.drop_constraint(
        "uq_tenant_memberships_id_tenant_account", "tenant_memberships", type_="unique"
    )
