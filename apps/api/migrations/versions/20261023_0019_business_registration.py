"""Add idempotent business self-registration records.

Revision ID: 20261023_0019
Revises: 20261023_0018
Created: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0019"
down_revision: str | None = "20261023_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "business_registrations": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("business_profiles", sa.Column("website_url", sa.Text()))
    op.create_table(
        "business_registrations",
        sa.Column(
            "registration_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("identity_id", UUID, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_business_registrations_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_business_registrations_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_business_registrations_principal_account",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["principal_identities.identity_id"],
            name="fk_business_registrations_identity",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_business_registrations_idempotency"),
        sa.UniqueConstraint("tenant_id", name="uq_business_registrations_tenant"),
    )


def downgrade() -> None:
    op.drop_table("business_registrations")
    op.drop_column("business_profiles", "website_url")
