"""Adapt render persistence for the free upload-first beta.

Revision ID: 20261017_0011
Revises: 20261017_0010
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0011"
down_revision: str | None = "20261017_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("ck_render_quotes_positive_cost", "render_quotes", type_="check")
    op.alter_column("render_quotes", "catalog_item_id", nullable=True)
    op.alter_column("render_quotes", "price_version_id", nullable=True)
    op.alter_column("render_quotes", "token_cost", nullable=True)
    op.create_check_constraint(
        "ck_render_quotes_nonnegative_cost",
        "render_quotes",
        "token_cost IS NULL OR token_cost >= 0",
    )
    op.add_column("render_quotes", sa.Column("principal_id", UUID))
    op.add_column("render_quotes", sa.Column("profile_id", UUID))
    op.add_column("render_quotes", sa.Column("item_asset_id", UUID))
    op.add_column("render_quotes", sa.Column("remaining_allowance", sa.SmallInteger()))
    op.add_column("render_quotes", sa.Column("provider", sa.String(40)))
    op.add_column("render_quotes", sa.Column("model_version", sa.String(120)))
    op.add_column("render_quotes", sa.Column("provider_region", sa.String(40)))
    op.create_check_constraint(
        "ck_render_quotes_beta_allowance",
        "render_quotes",
        "remaining_allowance IS NULL OR remaining_allowance BETWEEN 1 AND 3",
    )
    op.create_foreign_key(
        "fk_render_quotes_principal_account",
        "render_quotes",
        "principals",
        ["principal_id", "account_id"],
        ["principal_id", "account_id"],
    )
    op.create_foreign_key(
        "fk_render_quotes_profile",
        "render_quotes",
        "person_profiles",
        ["profile_id"],
        ["profile_id"],
    )
    op.create_foreign_key(
        "fk_render_quotes_item_asset_account",
        "render_quotes",
        "media_assets",
        ["account_id", "item_asset_id"],
        ["account_id", "asset_id"],
    )
    op.create_check_constraint(
        "ck_render_quotes_source_mode",
        "render_quotes",
        "(catalog_item_id IS NOT NULL AND price_version_id IS NOT NULL AND token_cost > 0) OR "
        "(profile_id IS NOT NULL AND principal_id IS NOT NULL AND item_asset_id IS NOT NULL "
        "AND remaining_allowance IS NOT NULL AND provider IS NOT NULL "
        "AND model_version IS NOT NULL AND provider_region IS NOT NULL)",
    )

    op.alter_column("render_jobs", "hold_id", nullable=True)

    op.alter_column("render_results", "catalog_item_id", nullable=True)
    op.add_column("render_results", sa.Column("source_item_asset_id", UUID))
    op.add_column("render_results", sa.Column("provider", sa.String(40)))
    op.add_column("render_results", sa.Column("provider_region", sa.String(40)))
    op.add_column("render_results", sa.Column("provider_request_id", sa.String(160)))
    op.create_foreign_key(
        "fk_render_results_item_asset_account",
        "render_results",
        "media_assets",
        ["account_id", "source_item_asset_id"],
        ["account_id", "asset_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_render_results_item_asset_account", "render_results", type_="foreignkey")
    op.drop_column("render_results", "provider_request_id")
    op.drop_column("render_results", "provider_region")
    op.drop_column("render_results", "provider")
    op.drop_column("render_results", "source_item_asset_id")
    op.alter_column("render_results", "catalog_item_id", nullable=False)
    op.alter_column("render_jobs", "hold_id", nullable=False)
    op.drop_constraint("ck_render_quotes_source_mode", "render_quotes", type_="check")
    op.drop_constraint("fk_render_quotes_item_asset_account", "render_quotes", type_="foreignkey")
    op.drop_constraint("fk_render_quotes_profile", "render_quotes", type_="foreignkey")
    op.drop_constraint("fk_render_quotes_principal_account", "render_quotes", type_="foreignkey")
    op.drop_constraint("ck_render_quotes_beta_allowance", "render_quotes", type_="check")
    op.drop_column("render_quotes", "provider_region")
    op.drop_column("render_quotes", "model_version")
    op.drop_column("render_quotes", "provider")
    op.drop_column("render_quotes", "remaining_allowance")
    op.drop_column("render_quotes", "item_asset_id")
    op.drop_column("render_quotes", "profile_id")
    op.drop_column("render_quotes", "principal_id")
    op.drop_constraint("ck_render_quotes_nonnegative_cost", "render_quotes", type_="check")
    op.alter_column("render_quotes", "token_cost", nullable=False)
    op.alter_column("render_quotes", "price_version_id", nullable=False)
    op.alter_column("render_quotes", "catalog_item_id", nullable=False)
    op.create_check_constraint("ck_render_quotes_positive_cost", "render_quotes", "token_cost > 0")
