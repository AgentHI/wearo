"""Add dataset input complexity classification.

Revision ID: 20261107_0081
Revises: 20261104_0080
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20261107_0081"
down_revision: str | None = "20261104_0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.benchmark_assets
      ADD COLUMN complexity text NOT NULL DEFAULT 'MEDIUM'
      CHECK (complexity IN ('SIMPLE','MEDIUM','COMPLEX'));
    ALTER TABLE cost_lab.dataset_generation_jobs
      ADD COLUMN complexity text NOT NULL DEFAULT 'MEDIUM'
      CHECK (complexity IN ('SIMPLE','MEDIUM','COMPLEX'));
    ALTER TABLE cost_lab.benchmark_runs
      ADD COLUMN input_complexity text NOT NULL DEFAULT 'MEDIUM'
      CHECK (input_complexity IN ('SIMPLE','MEDIUM','COMPLEX'));
    ALTER TABLE cost_lab.final_model_checks
      ADD COLUMN input_complexities jsonb NOT NULL DEFAULT
        '{"JEWELLERY":"MEDIUM","SAREE":"MEDIUM","DRESS":"MEDIUM"}'::jsonb;
    CREATE INDEX ix_cost_lab_assets_kind_complexity
      ON cost_lab.benchmark_assets(kind,complexity) WHERE replaced_at IS NULL;
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX cost_lab.ix_cost_lab_assets_kind_complexity;
    ALTER TABLE cost_lab.final_model_checks DROP COLUMN input_complexities;
    ALTER TABLE cost_lab.benchmark_runs DROP COLUMN input_complexity;
    ALTER TABLE cost_lab.dataset_generation_jobs DROP COLUMN complexity;
    ALTER TABLE cost_lab.benchmark_assets DROP COLUMN complexity;
    """)
