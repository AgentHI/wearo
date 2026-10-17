"""Add the durable beta render work queue.

Revision ID: 20261017_0012
Revises: 20261017_0011
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0012"
down_revision: str | None = "20261017_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "render_work_items": {
        "classification": "private",
        "owner_columns": ["account_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "render_work_items",
        sa.Column(
            "work_item_id",
            UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("available_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("leased_by", sa.String(120)),
        sa.Column("lease_expires_at", TIMESTAMP),
        sa.Column("last_error", sa.String(120)),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('PENDING', 'LEASED', 'DONE', 'DEAD')",
            name="ck_render_work_items_status",
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_render_work_items_attempts"),
        sa.CheckConstraint(
            "(status = 'LEASED') = (leased_by IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_render_work_items_lease",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "account_id"],
            ["render_jobs.job_id", "render_jobs.account_id"],
            name="fk_render_work_items_job_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("job_id", name="uq_render_work_items_job"),
    )
    op.create_index(
        "ix_render_work_items_claim",
        "render_work_items",
        ["status", "available_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_render_work_items_claim", table_name="render_work_items")
    op.drop_table("render_work_items")
