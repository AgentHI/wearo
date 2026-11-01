"""Track durable advertisement generation events.

Revision ID: 20261101_0058
Revises: 20261031_0057
Created: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20261101_0058"
down_revision: str | None = "20261031_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES = {
    "store_advertisement_generations": {
        "classification": "audit",
        "owner_columns": ["account_id", "tenant_id"],
    }
}


def upgrade() -> None:
    op.create_table(
        "store_advertisement_generations",
        sa.Column(
            "generation_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("advertisement_id", UUID, nullable=False),
        sa.Column("store_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["store_id"], ["business_stores.store_id"]),
    )
    op.create_index(
        "ix_store_advertisement_generations_tenant_store",
        "store_advertisement_generations",
        ["tenant_id", "store_id", "generated_at"],
    )
    op.execute("""INSERT INTO store_advertisement_generations
        (advertisement_id, store_id, tenant_id, account_id, generated_at, created_at, updated_at)
        SELECT advertisement_id, store_id, tenant_id, account_id,
               CASE WHEN attempt.number=1 THEN created_at ELSE updated_at END,
               CASE WHEN attempt.number=1 THEN created_at ELSE updated_at END,
               CASE WHEN attempt.number=1 THEN created_at ELSE updated_at END
        FROM store_advertisements
        CROSS JOIN LATERAL generate_series(1, ai_attempts) AS attempt(number)
        WHERE ai_attempts > 0""")


def downgrade() -> None:
    op.drop_index(
        "ix_store_advertisement_generations_tenant_store",
        table_name="store_advertisement_generations",
    )
    op.drop_table("store_advertisement_generations")
