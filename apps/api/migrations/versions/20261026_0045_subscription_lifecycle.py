"""Add explicit business subscription lifecycle state.

Revision ID: 20261026_0045
Revises: 20261026_0044
Created: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261026_0045"
down_revision: str | None = "20261026_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "business_subscriptions": {
        "classification": "financial",
        "owner_columns": ["account_id", "tenant_id"],
    }
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "business_subscriptions",
        sa.Column(
            "subscription_id",
            UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("plan_code", sa.String(40), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=False),
        sa.Column("next_billing_at", TIMESTAMP),
        sa.Column("trial_ends_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "state IN ('TRIAL', 'ACTIVE', 'PAYMENT_DUE', 'PAUSED', 'CANCELLED', 'EXPIRED')",
            name="ck_business_subscriptions_state",
        ),
        sa.CheckConstraint(
            "state <> 'TRIAL' OR trial_ends_at IS NOT NULL",
            name="ck_business_subscriptions_trial_end",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_business_subscriptions_tenant_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", name="uq_business_subscriptions_tenant"),
    )
    op.execute(
        """
        INSERT INTO business_subscriptions
          (tenant_id, account_id, plan_code, state, started_at, next_billing_at)
        SELECT tenant.tenant_id, tenant.account_id, COALESCE(plan.plan_code, 'LAUNCH'),
               CASE WHEN tenant.try_on_status='CANCELLED' THEN 'CANCELLED'
                    WHEN tenant.try_on_status='PAUSED' THEN 'PAUSED'
                    ELSE 'ACTIVE' END,
               COALESCE(plan.effective_from, tenant.created_at), plan.effective_until
        FROM business_tenants tenant
        LEFT JOIN LATERAL (
          SELECT plan_code, effective_from, effective_until FROM plan_assignments
          WHERE account_id=tenant.account_id AND tenant_id=tenant.tenant_id
          ORDER BY effective_from DESC LIMIT 1
        ) plan ON true
        """
    )


def downgrade() -> None:
    op.drop_table("business_subscriptions")
