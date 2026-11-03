"""Group identical benchmark inputs into model comparisons.

Revision ID: 20261103_0070
Revises: 20261103_0069
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20261103_0070"
down_revision: str | None = "20261103_0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.execute("""
    CREATE TABLE cost_lab.model_comparisons (
      comparison_id uuid PRIMARY KEY,
      person_result_tryon_id uuid NOT NULL REFERENCES cost_lab.tryon_runs(tryon_id),
      product_asset_id uuid NOT NULL REFERENCES cost_lab.benchmark_assets(asset_id),
      category text NOT NULL CHECK (category IN ('JEWELLERY','SAREE','DRESS')),
      output_quality text NOT NULL CHECK (output_quality IN ('LOW','MEDIUM','HIGH')),
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE cost_lab.model_comparison_entries (
      comparison_id uuid NOT NULL
        REFERENCES cost_lab.model_comparisons(comparison_id) ON DELETE CASCADE,
      run_id uuid NOT NULL UNIQUE REFERENCES cost_lab.benchmark_runs(run_id) ON DELETE CASCADE,
      model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
      PRIMARY KEY(comparison_id,model_id)
    );
    """)

def downgrade() -> None:
    op.execute("DROP TABLE cost_lab.model_comparison_entries")
    op.execute("DROP TABLE cost_lab.model_comparisons")
