"""Make final-check written comments optional while retaining scores.

Revision ID: 20261104_0076
Revises: 20261104_0075
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261104_0076"
down_revision: str | None = "20261104_0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE cost_lab.final_model_reviews
      DROP CONSTRAINT final_model_reviews_comment_check,
      ALTER COLUMN comment SET DEFAULT '',
      ADD CONSTRAINT ck_final_model_reviews_comment_length
        CHECK (length(comment) <= 4000);
    """)


def downgrade() -> None:
    op.execute("""
    DELETE FROM cost_lab.final_model_reviews WHERE length(btrim(comment)) = 0;
    ALTER TABLE cost_lab.final_model_reviews
      DROP CONSTRAINT ck_final_model_reviews_comment_length,
      ALTER COLUMN comment DROP DEFAULT,
      ADD CONSTRAINT final_model_reviews_comment_check
        CHECK (length(btrim(comment)) BETWEEN 1 AND 4000);
    """)
