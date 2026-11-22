"""Record optional marketing consent with photo consent evidence.

Revision ID: 20261122_0097
Revises: 20261122_0096
Created: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0097"
down_revision: str | None = "20261122_0096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "consent_records",
        sa.Column(
            "marketing_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "consent_records",
        sa.Column(
            "marketing_tenant_id",
            sa.Uuid(),
            sa.ForeignKey("business_tenants.tenant_id", ondelete="CASCADE"),
        ),
    )
    op.create_check_constraint(
        "ck_consent_records_marketing_scope",
        "consent_records",
        "NOT marketing_approved OR marketing_tenant_id IS NOT NULL",
    )
    op.add_column(
        "person_tryon_observations",
        sa.Column(
            "marketing_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("person_tryon_observations", "marketing_eligible")
    op.drop_constraint(
        "ck_consent_records_marketing_scope",
        "consent_records",
        type_="check",
    )
    op.drop_column("consent_records", "marketing_tenant_id")
    op.drop_column("consent_records", "marketing_approved")
