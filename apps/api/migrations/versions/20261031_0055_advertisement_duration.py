"""Add validity dates to store advertisements.

Revision ID: 20261031_0055
Revises: 20261031_0054
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0055"
down_revision: str | None = "20261031_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("store_advertisements", sa.Column("starts_on", sa.Date()))
    op.add_column("store_advertisements", sa.Column("ends_on", sa.Date()))
    op.execute("""UPDATE store_advertisements SET
        starts_on=(created_at AT TIME ZONE 'Asia/Kolkata')::date,
        ends_on=(created_at AT TIME ZONE 'Asia/Kolkata')::date""")
    op.alter_column("store_advertisements", "starts_on", nullable=False)
    op.alter_column("store_advertisements", "ends_on", nullable=False)
    op.create_check_constraint(
        "ck_store_advertisements_duration",
        "store_advertisements",
        "ends_on >= starts_on",
    )
    op.create_index(
        "ix_store_advertisements_store_duration",
        "store_advertisements",
        ["store_id", "starts_on", "ends_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_store_advertisements_store_duration", table_name="store_advertisements")
    op.drop_constraint("ck_store_advertisements_duration", "store_advertisements", type_="check")
    op.drop_column("store_advertisements", "ends_on")
    op.drop_column("store_advertisements", "starts_on")
