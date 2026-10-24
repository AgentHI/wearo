"""Add traceable tenant communication preferences.

Revision ID: 20261023_0027
Revises: 20261023_0026
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0027"
down_revision: str | None = "20261023_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "communication_preferences": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    }
}
UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "communication_preferences",
        sa.Column(
            "preference_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("channel IN ('EMAIL', 'SMS')", name="ck_communication_channel"),
        sa.CheckConstraint(
            "topic IN ('PRODUCT', 'BILLING', 'LEGAL')", name="ck_communication_topic"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_communication_preferences_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_communication_preferences_principal_account",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "principal_id",
            "channel",
            "topic",
            name="uq_communication_preferences_subject",
        ),
    )


def downgrade() -> None:
    op.drop_table("communication_preferences")
