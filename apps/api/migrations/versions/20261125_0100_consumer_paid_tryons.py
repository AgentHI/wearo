"""Connect consumer render jobs to retail-token usage records.

Revision ID: 20261125_0100
Revises: 20261125_0099
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261125_0100"
down_revision: str | None = "20261125_0099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "billable_usage_records",
        sa.Column("retail_price_id", UUID),
    )
    op.create_foreign_key(
        "fk_billable_usage_retail_price",
        "billable_usage_records",
        "retail_tryon_prices",
        ["retail_price_id"],
        ["retail_price_id"],
    )
    op.alter_column(
        "billable_usage_records",
        "price_version_id",
        existing_type=UUID,
        nullable=True,
    )
    op.create_check_constraint(
        "ck_billable_usage_one_price_source",
        "billable_usage_records",
        "num_nonnulls(price_version_id, retail_price_id) = 1",
    )

    op.add_column(
        "render_jobs",
        sa.Column("billable_usage_id", UUID),
    )
    op.create_foreign_key(
        "fk_render_jobs_billable_usage_account",
        "render_jobs",
        "billable_usage_records",
        ["billable_usage_id", "account_id"],
        ["usage_id", "account_id"],
    )
    op.create_unique_constraint(
        "uq_render_jobs_billable_usage",
        "render_jobs",
        ["billable_usage_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_render_jobs_billable_usage", "render_jobs", type_="unique")
    op.drop_constraint("fk_render_jobs_billable_usage_account", "render_jobs", type_="foreignkey")
    op.drop_column("render_jobs", "billable_usage_id")

    op.drop_constraint(
        "ck_billable_usage_one_price_source", "billable_usage_records", type_="check"
    )
    # The legacy schema requires a generic price-version reference. A downgrade is
    # therefore only safe when no retail-priced usage has been recorded yet.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM billable_usage_records WHERE price_version_id IS NULL
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade while retail-priced usage records exist';
          END IF;
        END $$
        """
    )
    op.alter_column(
        "billable_usage_records",
        "price_version_id",
        existing_type=UUID,
        nullable=False,
    )
    op.drop_constraint(
        "fk_billable_usage_retail_price", "billable_usage_records", type_="foreignkey"
    )
    op.drop_column("billable_usage_records", "retail_price_id")
