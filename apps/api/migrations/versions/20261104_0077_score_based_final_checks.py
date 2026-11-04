"""Mark the transition to score-based final checks without deleting judge history.

Revision ID: 20261104_0077
Revises: 20261104_0076
"""

from collections.abc import Sequence

revision: str = "20261104_0077"
down_revision: str | None = "20261104_0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing judgement rows are retained only as historical audit records.
    pass


def downgrade() -> None:
    pass
