"""Limit automatic media expiry to completed try-on results.

Revision ID: 20261128_0101
Revises: 20261125_0100
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261128_0101"
down_revision: str | None = "20261125_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    # Preserve explicit owner-deletion requests. Those rows are REQUESTED rather
    # than RETAINED and must continue through the deletion workflow.
    op.execute(
        """
        UPDATE media_assets
        SET retention_state = 'ACTIVE',
            delete_after = NULL,
            updated_at = now()
        WHERE purpose <> 'RENDER_RESULT'
          AND deletion_state = 'RETAINED'
          AND delete_after IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE media_assets
        SET retention_state = 'EXPIRING',
            delete_after = now() + interval '30 days',
            updated_at = now()
        WHERE purpose IN ('PRODUCT_SOURCE', 'ADVERTISEMENT')
          AND deletion_state = 'RETAINED'
          AND delete_after IS NULL
        """
    )
