"""Add category gates and tenant or concept-owned catalogue records.

Revision ID: 20261017_0004
Revises: 20261017_0003
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0004"
down_revision: str | None = "20261017_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "offering_categories": {"classification": "public", "owner_columns": []},
    "catalog_items": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "catalog_item_images": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "offering_categories",
        sa.Column(
            "category_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("offering", sa.String(24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "offering IN ('SHOP', 'BUSINESS', 'MIRROR_LITE')",
            name="ck_offering_categories_offering",
        ),
        sa.UniqueConstraint("offering", "code", name="uq_offering_categories_offering_code"),
    )

    op.create_table(
        "catalog_items",
        sa.Column("item_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID),
        sa.Column("tenant_id", UUID),
        sa.Column("concept_owner", sa.String(80)),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("item_code", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("width_mm", sa.Numeric(10, 2)),
        sa.Column("height_mm", sa.Numeric(10, 2)),
        sa.Column("depth_mm", sa.Numeric(10, 2)),
        sa.Column("seller_url", sa.Text()),
        sa.Column("seller_url_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("publish_state", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("quality_state", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(tenant_id IS NOT NULL AND account_id IS NOT NULL AND concept_owner IS NULL) OR "
            "(tenant_id IS NULL AND account_id IS NULL AND concept_owner IS NOT NULL)",
            name="ck_catalog_items_exact_owner",
        ),
        sa.CheckConstraint(
            "(source_type = 'GENUINE' AND tenant_id IS NOT NULL) OR "
            "(source_type = 'CONCEPT' AND concept_owner IS NOT NULL)",
            name="ck_catalog_items_source_owner",
        ),
        sa.CheckConstraint("source_type IN ('GENUINE', 'CONCEPT')", name="ck_catalog_items_source"),
        sa.CheckConstraint(
            "publish_state IN ('DRAFT', 'PUBLISHED', 'UNPUBLISHED')",
            name="ck_catalog_items_publish_state",
        ),
        sa.CheckConstraint(
            "quality_state IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_catalog_items_quality_state",
        ),
        sa.CheckConstraint(
            "publish_state <> 'PUBLISHED' OR quality_state = 'APPROVED'",
            name="ck_catalog_items_published_quality",
        ),
        sa.CheckConstraint(
            "seller_url_verified = false OR seller_url IS NOT NULL",
            name="ck_catalog_items_verified_url",
        ),
        sa.CheckConstraint(
            "width_mm IS NULL OR width_mm > 0", name="ck_catalog_items_width_positive"
        ),
        sa.CheckConstraint(
            "height_mm IS NULL OR height_mm > 0", name="ck_catalog_items_height_positive"
        ),
        sa.CheckConstraint(
            "depth_mm IS NULL OR depth_mm > 0", name="ck_catalog_items_depth_positive"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_catalog_items_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["offering_categories.category_id"], name="fk_catalog_items_category"
        ),
        sa.UniqueConstraint("item_id", "account_id", name="uq_catalog_items_id_account"),
    )
    op.create_index(
        "uq_catalog_items_tenant_code",
        "catalog_items",
        ["tenant_id", "item_code"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_catalog_items_concept_code",
        "catalog_items",
        ["concept_owner", "item_code"],
        unique=True,
        postgresql_where=sa.text("concept_owner IS NOT NULL"),
    )
    op.create_index(
        "ix_catalog_items_tenant_publish",
        "catalog_items",
        ["tenant_id", "publish_state", "category_id"],
    )
    op.execute(
        """
        CREATE FUNCTION enforce_catalogue_publish_gate() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.publish_state = 'PUBLISHED' AND NOT EXISTS (
                SELECT 1 FROM offering_categories c
                WHERE c.category_id = NEW.category_id AND c.enabled
            ) THEN
                RAISE EXCEPTION 'cannot publish into a disabled category';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_catalogue_publish_gate
        BEFORE INSERT OR UPDATE ON catalog_items
        FOR EACH ROW EXECUTE FUNCTION enforce_catalogue_publish_gate()
        """
    )

    op.create_table(
        "catalog_item_images",
        sa.Column("image_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("account_id", UUID),
        sa.Column("tenant_id", UUID),
        sa.Column("asset_id", UUID, nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("position >= 0", name="ck_catalog_item_images_position"),
        sa.ForeignKeyConstraint(
            ["item_id", "account_id"],
            ["catalog_items.item_id", "catalog_items.account_id"],
            name="fk_catalog_item_images_item_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_catalog_item_images_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["media_assets.asset_id"], name="fk_catalog_item_images_asset"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_catalog_item_images_tenant_account",
        ),
        sa.UniqueConstraint("item_id", "position", name="uq_catalog_item_images_item_position"),
        sa.UniqueConstraint("item_id", "asset_id", name="uq_catalog_item_images_item_asset"),
    )


def downgrade() -> None:
    op.drop_table("catalog_item_images")
    op.execute("DROP TRIGGER trg_catalogue_publish_gate ON catalog_items")
    op.execute("DROP FUNCTION enforce_catalogue_publish_gate()")
    op.drop_index("ix_catalog_items_tenant_publish", table_name="catalog_items")
    op.drop_index("uq_catalog_items_concept_code", table_name="catalog_items")
    op.drop_index("uq_catalog_items_tenant_code", table_name="catalog_items")
    op.drop_table("catalog_items")
    op.drop_table("offering_categories")
