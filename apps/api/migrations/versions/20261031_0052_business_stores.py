"""Add business stores, one store administrator, and store-owned agents.

Revision ID: 20261031_0052
Revises: 20261031_0051
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261031_0052"
down_revision: str | None = "20261031_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES = {
    "business_stores": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    }
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "business_stores",
        sa.Column("store_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("admin_principal_id", UUID),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="ck_business_stores_status"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_business_stores_tenant_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["admin_principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_business_stores_admin_account",
        ),
        sa.UniqueConstraint("store_id", "account_id", name="uq_business_stores_id_account"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_business_stores_tenant_code"),
        sa.UniqueConstraint("admin_principal_id", name="uq_business_stores_admin"),
    )
    op.execute(
        """INSERT INTO business_stores (tenant_id, account_id, name, code)
        SELECT tenant_id, account_id, 'Main Store', 'main'
        FROM business_tenants"""
    )
    op.add_column("business_agents", sa.Column("store_id", UUID))
    op.execute(
        """UPDATE business_agents a SET store_id=s.store_id
        FROM business_stores s
        WHERE s.tenant_id=a.tenant_id AND s.account_id=a.account_id AND s.code='main'"""
    )
    op.alter_column("business_agents", "store_id", nullable=False)
    op.create_foreign_key(
        "fk_business_agents_store_account",
        "business_agents",
        "business_stores",
        ["store_id", "account_id"],
        ["store_id", "account_id"],
    )
    op.create_index("ix_business_agents_store_status", "business_agents", ["store_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_business_agents_store_status", table_name="business_agents")
    op.drop_constraint("fk_business_agents_store_account", "business_agents", type_="foreignkey")
    op.drop_column("business_agents", "store_id")
    op.drop_table("business_stores")
