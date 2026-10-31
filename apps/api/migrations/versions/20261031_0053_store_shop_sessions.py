"""Associate sponsored customer sessions with a store.

Revision ID: 20261031_0053
Revises: 20261031_0052
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261031_0053"
down_revision: str | None = "20261031_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # Nullable preserves sessions created from the former business-level QR.
    op.add_column("business_sponsored_sessions", sa.Column("store_id", UUID))
    op.create_foreign_key(
        "fk_sponsored_sessions_store_account",
        "business_sponsored_sessions",
        "business_stores",
        ["store_id", "business_account_id"],
        ["store_id", "account_id"],
    )
    op.create_index(
        "ix_sponsored_sessions_store_created",
        "business_sponsored_sessions",
        ["store_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sponsored_sessions_store_created", table_name="business_sponsored_sessions")
    op.drop_constraint(
        "fk_sponsored_sessions_store_account", "business_sponsored_sessions", type_="foreignkey"
    )
    op.drop_column("business_sponsored_sessions", "store_id")
