"""Add business SmartAds creation, generation, activation, and scheduling.

Revision ID: 20261122_0095
Revises: 20261122_0094
Created: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261122_0095"
down_revision: str | None = "20261122_0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "business_smart_ads": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "business_smart_ad_generations": {
        "classification": "audit",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "business_smart_ad_schedules": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
}


def upgrade() -> None:
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PERSON_SOURCE', 'PRODUCT_SOURCE', 'RENDER_RESULT', "
        "'BUSINESS_LOGO', 'ADVERTISEMENT', 'SMART_AD')",
    )

    op.create_table(
        "business_smart_ads",
        sa.Column(
            "smart_ad_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("prompt", sa.String(2000), nullable=False),
        sa.Column("jewellery_asset_id", UUID, nullable=False),
        sa.Column("model_asset_id", UUID),
        sa.Column("creative_asset_id", UUID),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("accepted_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE')", name="ck_business_smart_ads_status"),
        sa.CheckConstraint(
            "status <> 'ACTIVE' OR (creative_asset_id IS NOT NULL AND accepted_at IS NOT NULL)",
            name="ck_business_smart_ads_active_creative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_business_smart_ads_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["jewellery_asset_id", "account_id"],
            ["media_assets.asset_id", "media_assets.account_id"],
            name="fk_business_smart_ads_jewellery",
        ),
        sa.ForeignKeyConstraint(
            ["model_asset_id", "account_id"],
            ["media_assets.asset_id", "media_assets.account_id"],
            name="fk_business_smart_ads_model",
        ),
        sa.ForeignKeyConstraint(
            ["creative_asset_id", "account_id"],
            ["media_assets.asset_id", "media_assets.account_id"],
            name="fk_business_smart_ads_creative",
        ),
        sa.UniqueConstraint("smart_ad_id", "account_id", name="uq_business_smart_ads_id_account"),
        sa.UniqueConstraint(
            "smart_ad_id",
            "tenant_id",
            "account_id",
            name="uq_business_smart_ads_id_tenant_account",
        ),
    )
    op.create_index(
        "ix_business_smart_ads_tenant_updated",
        "business_smart_ads",
        ["tenant_id", "account_id", "updated_at"],
    )

    op.create_table(
        "business_smart_ad_generations",
        sa.Column(
            "generation_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("smart_ad_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("generated_asset_id", UUID),
        sa.Column("status", sa.String(16), nullable=False, server_default="RESERVED"),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("generated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('RESERVED','COMPLETE','FAILED')",
            name="ck_business_smart_ad_generations_status",
        ),
        sa.ForeignKeyConstraint(
            ["smart_ad_id", "account_id"],
            ["business_smart_ads.smart_ad_id", "business_smart_ads.account_id"],
            name="fk_business_smart_ad_generations_ad",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["generated_asset_id", "account_id"],
            ["media_assets.asset_id", "media_assets.account_id"],
            name="fk_business_smart_ad_generations_asset",
        ),
    )
    op.create_index(
        "ix_business_smart_ad_generations_daily",
        "business_smart_ad_generations",
        ["tenant_id", "account_id", "generated_at"],
    )

    op.create_table(
        "business_smart_ad_schedules",
        sa.Column(
            "schedule_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("smart_ad_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("occasion", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False, server_default="EMAIL"),
        sa.Column("scheduled_for", TIMESTAMP, nullable=False),
        sa.Column("target_gender", sa.String(16), nullable=False, server_default="female"),
        sa.Column("target_age_min", sa.SmallInteger()),
        sa.Column("target_age_max", sa.SmallInteger()),
        sa.Column("target_user_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "public_token", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("channel IN ('EMAIL','WHATSAPP')", name="ck_smart_ad_schedules_channel"),
        sa.CheckConstraint(
            "target_gender IN ('all','female','male','non_binary')",
            name="ck_smart_ad_schedules_gender",
        ),
        sa.CheckConstraint(
            "target_age_min IS NULL OR target_age_min BETWEEN 1 AND 120",
            name="ck_smart_ad_schedules_age_min",
        ),
        sa.CheckConstraint(
            "target_age_max IS NULL OR target_age_max BETWEEN 1 AND 120",
            name="ck_smart_ad_schedules_age_max",
        ),
        sa.CheckConstraint(
            "target_age_min IS NULL OR target_age_max IS NULL OR target_age_min <= target_age_max",
            name="ck_smart_ad_schedules_age_order",
        ),
        sa.CheckConstraint(
            "target_user_count >= 0 AND queued_recipient_count >= 0",
            name="ck_smart_ad_schedules_counts",
        ),
        sa.ForeignKeyConstraint(
            ["smart_ad_id", "tenant_id", "account_id"],
            [
                "business_smart_ads.smart_ad_id",
                "business_smart_ads.tenant_id",
                "business_smart_ads.account_id",
            ],
            name="fk_business_smart_ad_schedules_ad",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("public_token", name="uq_business_smart_ad_schedules_public_token"),
    )
    op.create_index(
        "ix_business_smart_ad_schedules_due",
        "business_smart_ad_schedules",
        ["tenant_id", "account_id", "scheduled_for"],
    )

    op.execute(
        """INSERT INTO communication_templates
        (template_id, channel, template_key, category, display_name, subject, body,
         signature, status)
        VALUES
        (gen_random_uuid(), 'EMAIL', 'SMART_AD', 'NOTIFICATION', 'SmartAds campaign',
         '{{advertisement_title}} from {{business_name}}',
         '{{occasion}}\n\nDiscover {{advertisement_title}} from {{business_name}}.',
         'Team Wearo.ai', 'ACTIVE')"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM communication_templates WHERE channel='EMAIL' AND template_key='SMART_AD'"
    )
    op.drop_index("ix_business_smart_ad_schedules_due", table_name="business_smart_ad_schedules")
    op.drop_table("business_smart_ad_schedules")
    op.drop_index(
        "ix_business_smart_ad_generations_daily",
        table_name="business_smart_ad_generations",
    )
    op.drop_table("business_smart_ad_generations")
    op.drop_index("ix_business_smart_ads_tenant_updated", table_name="business_smart_ads")
    op.drop_table("business_smart_ads")
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PERSON_SOURCE', 'PRODUCT_SOURCE', 'RENDER_RESULT', "
        "'BUSINESS_LOGO', 'ADVERTISEMENT')",
    )
