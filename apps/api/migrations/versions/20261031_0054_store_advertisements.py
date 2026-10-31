"""Add premium store advertisement cards and daily activation.

Revision ID: 20261031_0054
Revises: 20261031_0053
Created: 2026-10-31
"""
# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261031_0054"
down_revision: str | None = "20261031_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)

TABLE_POLICIES = {
    "store_advertisements": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "store_advertisement_activations": {"classification": "private", "owner_columns": ["store_id"]},
}


def upgrade() -> None:
    # This is the plan/entitlement switch. It defaults on during the initial rollout.
    op.add_column(
        "business_tenants",
        sa.Column("advertisements_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PERSON_SOURCE', 'PRODUCT_SOURCE', 'RENDER_RESULT', 'BUSINESS_LOGO', 'ADVERTISEMENT')",
    )
    op.create_table(
        "store_advertisements",
        sa.Column(
            "advertisement_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("store_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("prompt", sa.String(1000)),
        sa.Column("asset_id", UUID, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("ai_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source IN ('AI', 'UPLOAD')", name="ck_store_advertisements_source"),
        sa.CheckConstraint(
            "ai_attempts BETWEEN 0 AND 3", name="ck_store_advertisements_ai_attempts"
        ),
        sa.ForeignKeyConstraint(
            ["store_id", "account_id"],
            ["business_stores.store_id", "business_stores.account_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id", "account_id"], ["media_assets.asset_id", "media_assets.account_id"]
        ),
    )
    op.create_index(
        "ix_store_advertisements_store_updated", "store_advertisements", ["store_id", "updated_at"]
    )
    op.create_table(
        "store_advertisement_activations",
        sa.Column("store_id", UUID, nullable=False),
        sa.Column("active_date", sa.Date(), nullable=False),
        sa.Column("advertisement_id", UUID, nullable=False),
        sa.Column("activated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["store_id"], ["business_stores.store_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["advertisement_id"], ["store_advertisements.advertisement_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("store_id", "active_date"),
    )


def downgrade() -> None:
    op.drop_table("store_advertisement_activations")
    op.drop_index("ix_store_advertisements_store_updated", table_name="store_advertisements")
    op.drop_table("store_advertisements")
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PERSON_SOURCE', 'PRODUCT_SOURCE', 'RENDER_RESULT', 'BUSINESS_LOGO')",
    )
    op.drop_column("business_tenants", "advertisements_enabled")
