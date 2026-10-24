"""Add business catalogue collections and prices.

Revision ID: 20261023_0016
Revises: 20261018_0015
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0016"
down_revision: str | None = "20261018_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "catalog_collections": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "catalog_collection_items": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("catalog_items", sa.Column("price_minor", sa.BigInteger()))
    op.add_column("catalog_items", sa.Column("currency", sa.String(3)))
    op.create_check_constraint(
        "ck_catalog_items_price_nonnegative",
        "catalog_items",
        "price_minor IS NULL OR price_minor >= 0",
    )
    op.create_check_constraint(
        "ck_catalog_items_price_complete",
        "catalog_items",
        "(price_minor IS NULL) = (currency IS NULL)",
    )
    op.create_check_constraint(
        "ck_catalog_items_currency_upper",
        "catalog_items",
        "currency IS NULL OR currency = upper(currency)",
    )

    op.create_table(
        "catalog_collections",
        sa.Column(
            "collection_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("publish_state", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "publish_state IN ('DRAFT', 'PUBLISHED', 'UNPUBLISHED')",
            name="ck_catalog_collections_publish_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_catalog_collections_tenant_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "collection_id", "account_id", name="uq_catalog_collections_id_account"
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_catalog_collections_tenant_name"),
    )
    op.create_index(
        "ix_catalog_collections_tenant_state",
        "catalog_collections",
        ["tenant_id", "publish_state"],
    )

    op.create_table(
        "catalog_collection_items",
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("position >= 0", name="ck_catalog_collection_items_position"),
        sa.ForeignKeyConstraint(
            ["collection_id", "account_id"],
            ["catalog_collections.collection_id", "catalog_collections.account_id"],
            name="fk_catalog_collection_items_collection_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "account_id"],
            ["catalog_items.item_id", "catalog_items.account_id"],
            name="fk_catalog_collection_items_item_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_catalog_collection_items_tenant_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "item_id", name="pk_catalog_collection_items"),
    )


def downgrade() -> None:
    op.drop_table("catalog_collection_items")
    op.drop_index("ix_catalog_collections_tenant_state", table_name="catalog_collections")
    op.drop_table("catalog_collections")
    op.drop_constraint("ck_catalog_items_currency_upper", "catalog_items", type_="check")
    op.drop_constraint("ck_catalog_items_price_complete", "catalog_items", type_="check")
    op.drop_constraint("ck_catalog_items_price_nonnegative", "catalog_items", type_="check")
    op.drop_column("catalog_items", "currency")
    op.drop_column("catalog_items", "price_minor")
