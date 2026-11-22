"""Replace the renewable consumer quota with a one-time registration grant.

Revision ID: 20261121_0089
Revises: 20261119_0088
Created: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261121_0089"
down_revision: str | None = "20261119_0088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES = {
    "consumer_free_tryon_grants": {
        "classification": "private",
        "owner_columns": ["account_id"],
    }
}
UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "consumer_free_tryon_grants",
        sa.Column("grant_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False, unique=True),
        sa.Column("grant_limit", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("successful_generations", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("active_job_id", UUID),
        sa.Column("granted_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("grant_limit BETWEEN 0 AND 3", name="ck_consumer_free_grant_limit"),
        sa.CheckConstraint(
            "successful_generations BETWEEN 0 AND grant_limit",
            name="ck_consumer_free_grant_usage",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_consumer_free_grant_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["active_job_id"],
            ["render_jobs.job_id"],
            name="fk_consumer_free_grant_active_job",
        ),
    )
    op.execute(
        """
        INSERT INTO consumer_free_tryon_grants
            (account_id, grant_limit, successful_generations, granted_at)
        SELECT account.account_id,
               3,
               LEAST(COALESCE(sum(usage.successful_generations), 0), 3)::smallint,
               account.created_at
        FROM accounts account
        LEFT JOIN generation_daily_usage usage ON usage.account_id=account.account_id
        WHERE account.kind='CONSUMER'
        GROUP BY account.account_id, account.created_at
        """
    )
    # Retain generation_daily_usage as immutable historical data. Runtime writes move to
    # consumer_free_tryon_grants after this revision, and keeping the source rows makes the
    # policy transition auditable and the migration non-destructive.


def downgrade() -> None:
    op.drop_table("consumer_free_tryon_grants")
