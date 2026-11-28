"""Allow a Cost Lab model to be selected directly for advertisement generation.

Revision ID: 20261128_0106
Revises: 20261128_0105
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261128_0106"
down_revision: str | None = "20261128_0105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cost_lab.ai_models
          ADD COLUMN advertisement_model boolean NOT NULL DEFAULT false;

        UPDATE cost_lab.ai_models AS model
        SET advertisement_model = true
        FROM cost_lab.production_model_releases AS release
        WHERE release.model_id = model.model_id
          AND release.advertisement_model
          AND release.retired_at IS NULL;

        CREATE UNIQUE INDEX uq_cost_lab_advertisement_model
          ON cost_lab.ai_models (advertisement_model)
          WHERE advertisement_model;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE cost_lab.production_model_releases AS release
        SET advertisement_model = false
        WHERE release.advertisement_model;

        UPDATE cost_lab.production_model_releases AS release
        SET advertisement_model = true
        WHERE release.release_id = (
          SELECT candidate.release_id
          FROM cost_lab.production_model_releases AS candidate
          JOIN cost_lab.ai_models AS model USING (model_id)
          WHERE model.advertisement_model
            AND candidate.retired_at IS NULL
          ORDER BY candidate.priority NULLS LAST, candidate.promoted_at DESC
          LIMIT 1
        );

        DROP INDEX cost_lab.uq_cost_lab_advertisement_model;
        ALTER TABLE cost_lab.ai_models DROP COLUMN advertisement_model;
        """
    )
