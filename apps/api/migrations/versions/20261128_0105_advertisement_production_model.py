"""Select one promoted production model for business advertisements.

Revision ID: 20261128_0105
Revises: 20261128_0104
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261128_0105"
down_revision: str | None = "20261128_0104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cost_lab.production_model_releases
          ADD COLUMN advertisement_model boolean NOT NULL DEFAULT false;

        UPDATE cost_lab.production_model_releases
        SET advertisement_model = true
        WHERE release_id = (
          SELECT r.release_id
          FROM cost_lab.production_model_releases r
          JOIN cost_lab.ai_models m USING(model_id)
          JOIN cost_lab.model_providers p USING(provider_id)
          WHERE r.retired_at IS NULL
            AND m.enabled AND p.enabled
          ORDER BY r.priority NULLS LAST, r.promoted_at DESC
          LIMIT 1
        );

        CREATE UNIQUE INDEX uq_active_advertisement_production_model
          ON cost_lab.production_model_releases (advertisement_model)
          WHERE advertisement_model AND retired_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX cost_lab.uq_active_advertisement_production_model;
        ALTER TABLE cost_lab.production_model_releases
          DROP COLUMN advertisement_model;
        """
    )
