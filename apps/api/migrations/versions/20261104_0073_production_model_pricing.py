"""Snapshot model pricing on production promotion.

Revision ID: 20261104_0073
Revises: 20261104_0072
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0073"
down_revision: str | None = "20261104_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.production_model_releases
      ADD COLUMN pricing_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
      ADD COLUMN pricing_effective_at timestamptz,
      ADD CONSTRAINT ck_production_release_pricing_snapshot
        CHECK (jsonb_typeof(pricing_snapshot)='array');

    UPDATE cost_lab.production_model_releases r SET
      pricing_snapshot=COALESCE((SELECT p.components FROM cost_lab.model_pricing p
        WHERE p.model_id=r.model_id AND p.effective_at <= r.promoted_at
        ORDER BY p.effective_at DESC LIMIT 1), '[]'::jsonb),
      pricing_effective_at=(SELECT p.effective_at FROM cost_lab.model_pricing p
        WHERE p.model_id=r.model_id AND p.effective_at <= r.promoted_at
        ORDER BY p.effective_at DESC LIMIT 1);
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.production_model_releases
      DROP CONSTRAINT ck_production_release_pricing_snapshot,
      DROP COLUMN pricing_effective_at,
      DROP COLUMN pricing_snapshot;
    """)
