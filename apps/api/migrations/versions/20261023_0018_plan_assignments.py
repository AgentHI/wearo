"""Add versioned account plan assignments.

Revision ID: 20261023_0018
Revises: 20261023_0017
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0018"
down_revision: str | None = "20261023_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "plan_assignments": {
        "classification": "financial",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "plan_assignments",
        sa.Column(
            "assignment_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("plan_code", sa.String(40), nullable=False),
        sa.Column("preview_limit", sa.Integer()),
        sa.Column("effective_from", TIMESTAMP, nullable=False),
        sa.Column("effective_until", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "preview_limit IS NULL OR preview_limit >= 0", name="ck_plan_assignments_preview_limit"
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_plan_assignments_window",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_plan_assignments_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_plan_assignments_tenant_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "account_id", "tenant_id", "effective_from", name="uq_plan_assignments_scope_from"
        ),
    )
    op.create_index(
        "ix_plan_assignments_active",
        "plan_assignments",
        ["account_id", "tenant_id", "effective_from", "effective_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_plan_assignments_active", table_name="plan_assignments")
    op.drop_table("plan_assignments")
