"""Add cancellation states to dataset generation.

Revision ID: 20261103_0069
Revises: 20261103_0068
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261103_0069"
down_revision: str | None = "20261103_0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.dataset_generation_jobs
      DROP CONSTRAINT dataset_generation_jobs_status_check,
      ADD CONSTRAINT dataset_generation_jobs_status_check CHECK
        (status IN ('QUEUED','RUNNING','CANCEL_REQUESTED','CANCELLED','COMPLETED','FAILED')),
      ADD COLUMN cancelled_items integer NOT NULL DEFAULT 0;

    ALTER TABLE cost_lab.dataset_generation_items
      DROP CONSTRAINT dataset_generation_items_status_check,
      ADD CONSTRAINT dataset_generation_items_status_check CHECK
        (status IN ('QUEUED','PROCESSING','SUCCEEDED','FAILED','CANCELLED'));
    """)


def downgrade() -> None:
    op.execute("""
    UPDATE cost_lab.dataset_generation_items SET status='FAILED' WHERE status='CANCELLED';
    UPDATE cost_lab.dataset_generation_jobs SET status='FAILED'
      WHERE status IN ('CANCEL_REQUESTED','CANCELLED');
    ALTER TABLE cost_lab.dataset_generation_items
      DROP CONSTRAINT dataset_generation_items_status_check,
      ADD CONSTRAINT dataset_generation_items_status_check CHECK
        (status IN ('QUEUED','PROCESSING','SUCCEEDED','FAILED'));
    ALTER TABLE cost_lab.dataset_generation_jobs
      DROP COLUMN cancelled_items,
      DROP CONSTRAINT dataset_generation_jobs_status_check,
      ADD CONSTRAINT dataset_generation_jobs_status_check CHECK
        (status IN ('QUEUED','RUNNING','COMPLETED','FAILED'));
    """)
