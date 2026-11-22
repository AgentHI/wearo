"""Allow optional Wearo marketing consent without a business tenant.

Revision ID: 20261122_0098
Revises: 20261122_0097
Created: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261122_0098"
down_revision: str | None = "20261122_0097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.drop_constraint(
        "ck_consent_records_marketing_scope",
        "consent_records",
        type_="check",
    )


def downgrade() -> None:
    op.create_check_constraint(
        "ck_consent_records_marketing_scope",
        "consent_records",
        "NOT marketing_approved OR marketing_tenant_id IS NOT NULL",
    )
