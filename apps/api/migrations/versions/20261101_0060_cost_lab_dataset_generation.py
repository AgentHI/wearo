"""Add one-time Cost Lab dataset generation jobs.

Revision ID: 20261101_0060
Revises: 20261101_0059
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261101_0060"
down_revision: str | None = "20261101_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE cost_lab.dataset_generation_jobs (
      job_id uuid PRIMARY KEY,
      model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
      status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
      total_items integer NOT NULL DEFAULT 31,
      completed_items integer NOT NULL DEFAULT 0,
      failed_items integer NOT NULL DEFAULT 0,
      total_cost_usd numeric(18,8) NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(),
      started_at timestamptz,
      finished_at timestamptz
    );
    CREATE TABLE cost_lab.dataset_generation_items (
      item_id uuid PRIMARY KEY,
      job_id uuid NOT NULL REFERENCES cost_lab.dataset_generation_jobs(job_id) ON DELETE CASCADE,
      ordinal integer NOT NULL,
      kind text NOT NULL CHECK (kind IN ('PERSON','JEWELLERY','SAREE','DRESS')),
      prompt text NOT NULL,
      status text NOT NULL CHECK (status IN ('QUEUED','PROCESSING','SUCCEEDED','FAILED')),
      attempts integer NOT NULL DEFAULT 0,
      provider_request_id text,
      asset_id uuid REFERENCES cost_lab.benchmark_assets(asset_id),
      usage jsonb NOT NULL DEFAULT '{}',
      cost_usd numeric(18,8) NOT NULL DEFAULT 0,
      error_detail text,
      created_at timestamptz NOT NULL DEFAULT now(),
      finished_at timestamptz,
      UNIQUE(job_id, ordinal)
    );
    CREATE INDEX ix_cost_lab_dataset_items_claim
      ON cost_lab.dataset_generation_items(status, created_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE cost_lab.dataset_generation_items")
    op.execute("DROP TABLE cost_lab.dataset_generation_jobs")
