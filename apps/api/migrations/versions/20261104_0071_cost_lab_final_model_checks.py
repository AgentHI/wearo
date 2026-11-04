"""Add final model checks, human reviews, judge decisions and production registry.

Revision ID: 20261104_0071
Revises: 20261103_0070
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0071"
down_revision: str | None = "20261103_0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE cost_lab.final_model_checks (
      check_id uuid PRIMARY KEY,
      model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
      person_asset_id uuid NOT NULL REFERENCES cost_lab.benchmark_assets(asset_id),
      status text NOT NULL CHECK (status IN
        ('GENERATING','REVIEW_PENDING','JUDGING','RECOMMENDED','NOT_RECOMMENDED','PROMOTED','FAILED')),
      required_reviews integer NOT NULL DEFAULT 12 CHECK (required_reviews = 12),
      created_by text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      judged_at timestamptz,
      promoted_at timestamptz
    );
    CREATE INDEX ix_final_model_checks_status
      ON cost_lab.final_model_checks(status, created_at DESC);

    CREATE TABLE cost_lab.final_model_check_runs (
      check_id uuid NOT NULL REFERENCES cost_lab.final_model_checks(check_id) ON DELETE CASCADE,
      run_id uuid NOT NULL UNIQUE REFERENCES cost_lab.benchmark_runs(run_id) ON DELETE CASCADE,
      category text NOT NULL CHECK (category IN ('JEWELLERY','SAREE','DRESS')),
      quality text NOT NULL CHECK (quality IN ('LOW','MEDIUM','HIGH')),
      expected_outputs integer NOT NULL CHECK (expected_outputs IN (1,2)),
      PRIMARY KEY(check_id,category,quality)
    );

    CREATE TABLE cost_lab.final_model_reviews (
      review_id uuid PRIMARY KEY,
      check_id uuid NOT NULL REFERENCES cost_lab.final_model_checks(check_id) ON DELETE CASCADE,
      tryon_id uuid NOT NULL UNIQUE REFERENCES cost_lab.tryon_runs(tryon_id) ON DELETE CASCADE,
      score smallint NOT NULL CHECK (score BETWEEN 1 AND 10),
      comment text NOT NULL CHECK (length(btrim(comment)) BETWEEN 1 AND 4000),
      reviewed_by text NOT NULL,
      reviewed_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_final_model_reviews_check ON cost_lab.final_model_reviews(check_id);

    CREATE TABLE cost_lab.final_model_judgements (
      judgement_id uuid PRIMARY KEY,
      check_id uuid NOT NULL UNIQUE
        REFERENCES cost_lab.final_model_checks(check_id) ON DELETE CASCADE,
      judge_model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
      recommend_production boolean NOT NULL,
      confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
      rationale text NOT NULL,
      score_summary jsonb NOT NULL,
      raw_response jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE cost_lab.production_model_releases (
      release_id uuid PRIMARY KEY,
      model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
      final_check_id uuid NOT NULL UNIQUE REFERENCES cost_lab.final_model_checks(check_id),
      promoted_by text NOT NULL,
      promoted_at timestamptz NOT NULL DEFAULT now(),
      retired_at timestamptz,
      CONSTRAINT uq_one_active_production_model EXCLUDE USING gist
        (tstzrange(promoted_at, retired_at, '[)') WITH &&)
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE cost_lab.production_model_releases")
    op.execute("DROP TABLE cost_lab.final_model_judgements")
    op.execute("DROP TABLE cost_lab.final_model_reviews")
    op.execute("DROP TABLE cost_lab.final_model_check_runs")
    op.execute("DROP TABLE cost_lab.final_model_checks")
