"""Add shared business platform administration foundations.

Revision ID: 20261023_0017
Revises: 20261023_0016
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0017"
down_revision: str | None = "20261023_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "business_profiles": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "business_profile_change_requests": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "business_agents": {"classification": "private", "owner_columns": ["account_id", "tenant_id"]},
    "business_allowance_policies": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "business_user_allowances": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "business_shop_links": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "legal_notices": {"classification": "public", "owner_columns": []},
    "legal_notice_acceptances": {
        "classification": "audit",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "support_access_grants": {
        "classification": "audit",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB()


def _tenant_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "account_id"],
        ["business_tenants.tenant_id", "business_tenants.account_id"],
        name=name,
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "business_profiles",
        sa.Column("tenant_id", UUID, primary_key=True),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("operating_profile", sa.String(32), nullable=False),
        sa.Column("jurisdiction", sa.String(2), nullable=False),
        sa.Column("billing_email", sa.String(320), nullable=False),
        sa.Column("billing_phone", sa.String(32)),
        sa.Column("billing_address", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tax_identifier", sa.String(80)),
        sa.Column("logo_asset_id", UUID),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "operating_profile IN ('BOUTIQUE', 'CLOTHING_RETAILER', "
            "'JEWELLERY_RETAILER', 'ENTERPRISE_CHAIN', 'OTHER')",
            name="ck_business_profiles_operating_profile",
        ),
        sa.CheckConstraint("jurisdiction ~ '^[A-Z]{2}$'", name="ck_business_profiles_jurisdiction"),
        _tenant_fk("fk_business_profiles_tenant_account"),
        sa.ForeignKeyConstraint(
            ["account_id", "logo_asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_business_profiles_logo_account",
        ),
        sa.UniqueConstraint("tenant_id", "account_id", name="uq_business_profiles_tenant_account"),
    )

    op.create_table(
        "business_profile_change_requests",
        sa.Column(
            "request_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("requested_by_principal_id", UUID, nullable=False),
        sa.Column("requested_profile", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "state IN ('OPEN', 'APPROVED', 'REJECTED')", name="ck_business_profile_requests_state"
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_business_profile_requests_reason"),
        _tenant_fk("fk_business_profile_requests_tenant_account"),
        sa.ForeignKeyConstraint(
            ["requested_by_principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_business_profile_requests_actor_account",
        ),
    )

    op.create_table(
        "business_agents",
        sa.Column("agent_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("principal_id", UUID),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("normalized_mobile", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'DELETED')", name="ck_business_agents_status"
        ),
        _tenant_fk("fk_business_agents_tenant_account"),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_business_agents_principal_account",
        ),
        sa.UniqueConstraint(
            "tenant_id", "normalized_mobile", name="uq_business_agents_tenant_mobile"
        ),
        sa.UniqueConstraint("agent_id", "account_id", name="uq_business_agents_id_account"),
    )

    op.create_table(
        "business_allowance_policies",
        sa.Column("tenant_id", UUID, primary_key=True),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("default_try_on_limit", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(16), nullable=False, server_default="DAY"),
        sa.Column("updated_by_principal_id", UUID, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "default_try_on_limit >= 0", name="ck_business_allowance_default_nonnegative"
        ),
        sa.CheckConstraint(
            "period IN ('DAY', 'MONTH', 'LIFETIME')", name="ck_business_allowance_period"
        ),
        _tenant_fk("fk_business_allowance_policies_tenant_account"),
        sa.ForeignKeyConstraint(
            ["updated_by_principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_business_allowance_policies_actor_account",
        ),
    )

    op.create_table(
        "business_user_allowances",
        sa.Column(
            "allowance_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("normalized_mobile", sa.String(32), nullable=False),
        sa.Column("limit_adjustment", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_started_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_principal_id", UUID, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("used_count >= 0", name="ck_business_user_allowances_used_nonnegative"),
        _tenant_fk("fk_business_user_allowances_tenant_account"),
        sa.ForeignKeyConstraint(
            ["updated_by_principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_business_user_allowances_actor_account",
        ),
        sa.UniqueConstraint(
            "tenant_id", "normalized_mobile", name="uq_business_user_allowances_tenant_mobile"
        ),
    )

    op.create_table(
        "business_shop_links",
        sa.Column("tenant_id", UUID, primary_key=True),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column(
            "public_token", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("caption", sa.String(80), nullable=False, server_default="Buy confidently!"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        _tenant_fk("fk_business_shop_links_tenant_account"),
        sa.UniqueConstraint("public_token", name="uq_business_shop_links_public_token"),
    )

    op.create_table(
        "legal_notices",
        sa.Column("notice_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notice_type", sa.String(40), nullable=False),
        sa.Column("offering", sa.String(24), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("content_url", sa.Text(), nullable=False),
        sa.Column("effective_at", TIMESTAMP, nullable=False),
        sa.Column("retired_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "retired_at IS NULL OR retired_at > effective_at", name="ck_legal_notices_window"
        ),
        sa.UniqueConstraint(
            "notice_type", "offering", "version", name="uq_legal_notices_type_offering_version"
        ),
    )

    op.create_table(
        "legal_notice_acceptances",
        sa.Column(
            "acceptance_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("notice_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("accepted_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["notice_id"], ["legal_notices.notice_id"], name="fk_notice_acceptances_notice"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_notice_acceptances_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_notice_acceptances_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_notice_acceptances_principal_account",
        ),
        sa.UniqueConstraint(
            "notice_id", "principal_id", "tenant_id", name="uq_notice_acceptances_subject"
        ),
    )

    op.create_table(
        "support_access_grants",
        sa.Column("grant_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("admin_id", UUID, nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("revoked_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "scope IN ('CASE_METADATA', 'BILLING', 'RENDER_METADATA', 'PRIVATE_MEDIA')",
            name="ck_support_access_grants_scope",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_support_access_grants_reason"),
        sa.CheckConstraint("expires_at > created_at", name="ck_support_access_grants_expiry"),
        sa.ForeignKeyConstraint(
            ["case_id", "account_id"],
            ["operation_cases.case_id", "operation_cases.account_id"],
            name="fk_support_access_grants_case_account",
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admin_identities.admin_id"], name="fk_support_access_grants_admin"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_support_access_grants_tenant_account",
        ),
    )
    op.create_index(
        "ix_support_access_grants_active",
        "support_access_grants",
        ["admin_id", "expires_at", "revoked_at"],
    )

    op.add_column("invoices", sa.Column("business_snapshot", JSONB))
    op.add_column("invoices", sa.Column("tax_snapshot", JSONB))
    op.add_column("invoices", sa.Column("document_url", sa.Text()))


def downgrade() -> None:
    op.drop_column("invoices", "document_url")
    op.drop_column("invoices", "tax_snapshot")
    op.drop_column("invoices", "business_snapshot")
    op.drop_index("ix_support_access_grants_active", table_name="support_access_grants")
    op.drop_table("support_access_grants")
    op.drop_table("legal_notice_acceptances")
    op.drop_table("legal_notices")
    op.drop_table("business_shop_links")
    op.drop_table("business_user_allowances")
    op.drop_table("business_allowance_policies")
    op.drop_table("business_agents")
    op.drop_table("business_profile_change_requests")
    op.drop_table("business_profiles")
