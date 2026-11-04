"""Use a dedicated OpenAI text judge and add the 90-point promotion gate.

Revision ID: 20261104_0072
Revises: 20261104_0071
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0072"
down_revision: str | None = "20261104_0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.final_model_judgements
      ALTER COLUMN judge_model_id DROP NOT NULL,
      ADD COLUMN judge_provider_id uuid REFERENCES cost_lab.model_providers(provider_id),
      ADD COLUMN judge_model_identifier text,
      ADD COLUMN llm_recommend_production boolean,
      ADD COLUMN score_percentage numeric(5,2)
        CHECK (score_percentage BETWEEN 0 AND 100);

    UPDATE cost_lab.final_model_judgements j SET
      judge_provider_id=m.provider_id,
      judge_model_identifier=m.api_identifier,
      llm_recommend_production=j.recommend_production,
      score_percentage=LEAST(100, GREATEST(0,
        COALESCE((j.score_summary->>'average_score')::numeric * 10, 0)))
    FROM cost_lab.ai_models m WHERE m.model_id=j.judge_model_id;

    ALTER TABLE cost_lab.final_model_judgements
      ALTER COLUMN judge_provider_id SET NOT NULL,
      ALTER COLUMN judge_model_identifier SET NOT NULL,
      ALTER COLUMN llm_recommend_production SET NOT NULL,
      ALTER COLUMN score_percentage SET NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
    DELETE FROM cost_lab.final_model_judgements WHERE judge_model_id IS NULL;
    ALTER TABLE cost_lab.final_model_judgements
      ALTER COLUMN judge_model_id SET NOT NULL,
      DROP COLUMN score_percentage,
      DROP COLUMN llm_recommend_production,
      DROP COLUMN judge_model_identifier,
      DROP COLUMN judge_provider_id;
    """)
