"""Add platform and business-type try-on controls.

Revision ID: 20261026_0048
Revises: 20261026_0047
Created: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261026_0048"
down_revision: str | None = "20261026_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES = {"platform_tryon_controls": {"classification": "operational"}}
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "platform_tryon_controls",
        sa.Column(
            "control_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "scope IN ('PLATFORM', 'BUSINESS_TYPE')", name="ck_tryon_controls_scope"
        ),
        sa.UniqueConstraint("scope", "scope_key", name="uq_tryon_controls_scope_key"),
    )
    op.execute(
        "INSERT INTO platform_tryon_controls (scope, scope_key, paused) "
        "VALUES ('PLATFORM', 'ALL', false)"
    )


def downgrade() -> None:
    op.drop_table("platform_tryon_controls")
