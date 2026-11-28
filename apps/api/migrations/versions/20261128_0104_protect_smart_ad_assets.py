"""Protect referenced SmartAds assets from automatic media purging.

Revision ID: 20261128_0104
Revises: 20261128_0103
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261128_0104"
down_revision: str | None = "20261128_0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    # A referenced SmartAds asset is still part of an admin-managed ad, even if
    # an older retention policy accidentally placed it in the deletion queue.
    op.execute(
        """
        UPDATE media_assets AS asset
        SET deletion_state = 'RETAINED',
            retention_state = 'ACTIVE',
            delete_after = NULL,
            updated_at = now()
        WHERE asset.purpose = 'SMART_AD'
          AND asset.deletion_state <> 'DELETED'
          AND asset.object_key IS NOT NULL
          AND (
            EXISTS (
              SELECT 1
              FROM business_smart_ads AS ad
              WHERE ad.jewellery_asset_id = asset.asset_id
                 OR ad.model_asset_id = asset.asset_id
                 OR ad.creative_asset_id = asset.asset_id
            )
            OR EXISTS (
              SELECT 1
              FROM business_smart_ad_generations AS generation
              WHERE generation.generated_asset_id = asset.asset_id
            )
          )
        """
    )


def downgrade() -> None:
    # Restoring a prior accidental deletion deadline would put retained customer
    # content back at risk, so this data repair is intentionally not reversed.
    pass
