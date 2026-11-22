"""Use the SmartAds advertisement caption as the email subject.

Revision ID: 20261122_0096
Revises: 20261122_0095
Created: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261122_0096"
down_revision: str | None = "20261122_0095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.execute(
        """
        UPDATE communication_templates
        SET subject = '{{advertisement_title}}'
        WHERE channel = 'EMAIL'
          AND template_key = 'SMART_AD'
          AND status = 'ACTIVE'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE communication_templates
        SET subject = '{{advertisement_title}} from {{business_name}}'
        WHERE channel = 'EMAIL'
          AND template_key = 'SMART_AD'
          AND status = 'ACTIVE'
        """
    )
