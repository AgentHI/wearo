"""Add dual-verification challenges for business owner email changes.

Revision ID: 20261128_0103
Revises: 20261128_0102
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261128_0103"
down_revision: str | None = "20261128_0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "owner_email_change_challenges": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id", "principal_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "owner_email_change_challenges",
        sa.Column("challenge_id", UUID, primary_key=True),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("current_email", sa.String(320), nullable=False),
        sa.Column("new_email", sa.String(320), nullable=False),
        sa.Column("current_code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("new_code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("consumed_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 5", name="ck_owner_email_change_challenges_attempts"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_owner_email_change_challenges_tenant_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_owner_email_change_challenges_principal_account",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_owner_email_change_challenges_principal_time",
        "owner_email_change_challenges",
        ["principal_id", "created_at"],
    )
    op.create_index(
        "ix_owner_email_change_challenges_expiry",
        "owner_email_change_challenges",
        ["expires_at", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_owner_email_change_challenges_expiry",
        table_name="owner_email_change_challenges",
    )
    op.drop_index(
        "ix_owner_email_change_challenges_principal_time",
        table_name="owner_email_change_challenges",
    )
    op.drop_table("owner_email_change_challenges")
