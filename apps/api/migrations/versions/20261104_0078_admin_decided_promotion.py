"""Make final promotion an administrator decision after scoring.

Revision ID: 20261104_0078
Revises: 20261104_0077
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0078"
down_revision: str | None = "20261104_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.final_model_checks
      DROP CONSTRAINT final_model_checks_status_check;
    UPDATE cost_lab.final_model_checks SET status='SCORED'
      WHERE status IN ('RECOMMENDED','NOT_RECOMMENDED');
    ALTER TABLE cost_lab.final_model_checks
      ADD CONSTRAINT final_model_checks_status_check CHECK (status IN
        ('GENERATING','REVIEW_PENDING','SCORED','PROMOTED','FAILED'));
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.final_model_checks
      DROP CONSTRAINT final_model_checks_status_check;
    UPDATE cost_lab.final_model_checks SET status='NOT_RECOMMENDED' WHERE status='SCORED';
    ALTER TABLE cost_lab.final_model_checks
      ADD CONSTRAINT final_model_checks_status_check CHECK (status IN
        ('GENERATING','REVIEW_PENDING','JUDGING','RECOMMENDED',
         'NOT_RECOMMENDED','PROMOTED','FAILED'));
    """)
