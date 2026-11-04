"""Store LLM recommendations for production quality levels.

Revision ID: 20261104_0075
Revises: 20261104_0074
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0075"
down_revision: str | None = "20261104_0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.final_model_judgements
      ADD COLUMN minimum_recommended_quality text
        CHECK (minimum_recommended_quality IN ('LOW','MEDIUM','HIGH')),
      ADD COLUMN recommended_quality_levels jsonb NOT NULL DEFAULT '[]'::jsonb,
      ADD CONSTRAINT ck_judgement_recommended_quality_levels CHECK (
        jsonb_typeof(recommended_quality_levels)='array'
        AND recommended_quality_levels <@ '["LOW","MEDIUM","HIGH"]'::jsonb
      );

    UPDATE cost_lab.final_model_judgements
    SET recommended_quality_levels='["LOW","MEDIUM","HIGH"]'::jsonb,
        minimum_recommended_quality='LOW'
    WHERE recommend_production=true;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.final_model_judgements
      DROP CONSTRAINT ck_judgement_recommended_quality_levels,
      DROP COLUMN recommended_quality_levels,
      DROP COLUMN minimum_recommended_quality;
    """)
