"""Allow multiple active production models and assign routing priority.

Revision ID: 20261104_0079
Revises: 20261104_0078
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0079"
down_revision: str | None = "20261104_0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.production_model_releases
      DROP CONSTRAINT uq_one_active_production_model;
    ALTER TABLE cost_lab.production_model_releases
      ADD COLUMN priority integer;
    WITH ranked AS (
      SELECT release_id,row_number() OVER (ORDER BY promoted_at DESC) AS priority
      FROM cost_lab.production_model_releases WHERE retired_at IS NULL
    )
    UPDATE cost_lab.production_model_releases r SET priority=ranked.priority
      FROM ranked WHERE ranked.release_id=r.release_id;
    ALTER TABLE cost_lab.production_model_releases
      ADD CONSTRAINT production_model_priority_positive
      CHECK (priority IS NULL OR priority > 0);
    CREATE UNIQUE INDEX uq_active_production_model_priority
      ON cost_lab.production_model_releases(priority) WHERE retired_at IS NULL;
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX cost_lab.uq_active_production_model_priority;
    ALTER TABLE cost_lab.production_model_releases
      DROP CONSTRAINT production_model_priority_positive;
    WITH keep AS (
      SELECT release_id FROM cost_lab.production_model_releases
      WHERE retired_at IS NULL ORDER BY priority LIMIT 1
    )
    UPDATE cost_lab.production_model_releases SET retired_at=now()
      WHERE retired_at IS NULL AND release_id NOT IN (SELECT release_id FROM keep);
    ALTER TABLE cost_lab.production_model_releases DROP COLUMN priority;
    ALTER TABLE cost_lab.production_model_releases
      ADD CONSTRAINT uq_one_active_production_model EXCLUDE USING gist
      (tstzrange(promoted_at, retired_at, '[)') WITH &&);
    """)
