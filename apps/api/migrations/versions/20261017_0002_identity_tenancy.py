"""Add the identity, paying-account, and tenant authorization foundation.

Revision ID: 20261017_0002
Revises: 20261017_0001
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0002"
down_revision: str | None = "20261017_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "accounts": {"classification": "private", "owner_columns": ["account_id"]},
    "principals": {"classification": "private", "owner_columns": ["account_id"]},
    "principal_identities": {"classification": "private", "owner_columns": ["account_id"]},
    "business_tenants": {
        "classification": "private",
        "owner_columns": ["tenant_id", "account_id"],
    },
    "tenant_memberships": {
        "classification": "private",
        "owner_columns": ["tenant_id", "account_id"],
    },
    "sessions": {"classification": "private", "owner_columns": ["account_id"]},
    "offering_entitlements": {
        "classification": "private",
        "owner_columns": ["tenant_id", "account_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column(
            "account_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('CONSUMER', 'TENANT')", name="ck_accounts_kind"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')", name="ck_accounts_status"
        ),
        sa.UniqueConstraint("account_id", "kind", name="uq_accounts_id_kind"),
    )

    op.create_table(
        "principals",
        sa.Column(
            "principal_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("account_kind", sa.String(16), nullable=False),
        sa.Column("principal_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(principal_type = 'CONSUMER' AND account_kind = 'CONSUMER') OR "
            "(principal_type = 'BUSINESS' AND account_kind = 'TENANT')",
            name="ck_principals_type_account_kind",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')", name="ck_principals_status"
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "account_kind"],
            ["accounts.account_id", "accounts.kind"],
            name="fk_principals_account_kind",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("principal_id", "account_id", name="uq_principals_id_account"),
    )
    op.create_index(
        "uq_principals_consumer_account",
        "principals",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("principal_type = 'CONSUMER'"),
    )

    op.create_table(
        "principal_identities",
        sa.Column(
            "identity_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("normalized_value", sa.String(320), nullable=False),
        sa.Column("verified_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("channel IN ('PHONE', 'EMAIL')", name="ck_principal_identities_channel"),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_principal_identities_principal_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "channel", "normalized_value", name="uq_principal_identities_channel_value"
        ),
        sa.UniqueConstraint(
            "principal_id", "channel", name="uq_principal_identities_principal_channel"
        ),
    )

    op.create_table(
        "business_tenants",
        sa.Column("tenant_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("account_kind", sa.String(16), nullable=False, server_default="TENANT"),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("account_kind = 'TENANT'", name="ck_business_tenants_account_kind"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')", name="ck_business_tenants_status"
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "account_kind"],
            ["accounts.account_id", "accounts.kind"],
            name="fk_business_tenants_account_kind",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("account_id", name="uq_business_tenants_account"),
        sa.UniqueConstraint("slug", name="uq_business_tenants_slug"),
        sa.UniqueConstraint("tenant_id", "account_id", name="uq_business_tenants_id_account"),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column(
            "membership_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("revoked_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('OWNER', 'ASSOCIATE')", name="ck_tenant_memberships_role"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_tenant_memberships_tenant_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_tenant_memberships_principal_account",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_tenant_memberships_active_principal",
        "tenant_memberships",
        ["tenant_id", "principal_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "sessions",
        sa.Column(
            "session_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("auth_realm", sa.String(16), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("revoked_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("auth_realm IN ('SHOP', 'BUSINESS')", name="ck_sessions_auth_realm"),
        sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_sessions_principal_account",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sessions_principal_active", "sessions", ["principal_id", "expires_at"])

    op.create_table(
        "offering_entitlements",
        sa.Column(
            "entitlement_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("offering", sa.String(24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("effective_from", TIMESTAMP, nullable=False),
        sa.Column("effective_until", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "offering IN ('SHOP', 'BUSINESS', 'MIRROR_LITE')",
            name="ck_offering_entitlements_offering",
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_offering_entitlements_window",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_offering_entitlements_tenant_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_offering_entitlements_account"
        ),
        sa.UniqueConstraint(
            "account_id",
            "offering",
            "effective_from",
            name="uq_offering_entitlements_account_offering_from",
        ),
    )


def downgrade() -> None:
    op.drop_table("offering_entitlements")
    op.drop_index("ix_sessions_principal_active", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("uq_tenant_memberships_active_principal", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_table("business_tenants")
    op.drop_table("principal_identities")
    op.drop_index("uq_principals_consumer_account", table_name="principals")
    op.drop_table("principals")
    op.drop_table("accounts")
