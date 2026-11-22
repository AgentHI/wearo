"""Track distinct people and their store-scoped try-on observations.

Revision ID: 20261122_0094
Revises: 20261122_0093
Created: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261122_0094"
down_revision: str | None = "20261122_0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "account_persons": {"classification": "private", "owner_columns": ["account_id"]},
    "person_tryon_observations": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)
AGE_RANGE_VALUES = "'unknown','under_10','10_19','20_29','30_39','40_49','50_59','60_plus'"


def upgrade() -> None:
    op.create_table(
        "account_persons",
        sa.Column("person_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        # This always references an uploaded PERSON_SOURCE asset, never a generated result.
        sa.Column("source_person_asset_id", UUID, nullable=False),
        sa.Column("person_category", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("gender", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("age_range", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("estimated_age", sa.SmallInteger()),
        # TRY_ON consent does not grant advertising use. A separate consent flow may set this.
        sa.Column("marketing_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", TIMESTAMP, nullable=False),
        sa.Column("last_seen_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "person_category IN ('unknown','girl','woman')",
            name="ck_account_persons_category",
        ),
        sa.CheckConstraint(
            "gender IN ('unknown','female','male','non_binary')",
            name="ck_account_persons_gender",
        ),
        sa.CheckConstraint(
            f"age_range IN ({AGE_RANGE_VALUES})",
            name="ck_account_persons_age_range",
        ),
        sa.CheckConstraint(
            "estimated_age IS NULL OR estimated_age BETWEEN 1 AND 120",
            name="ck_account_persons_estimated_age",
        ),
        sa.CheckConstraint(
            "last_seen_at >= first_seen_at",
            name="ck_account_persons_seen_order",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_account_persons_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "source_person_asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_account_persons_source_asset",
        ),
        sa.UniqueConstraint("person_id", "account_id", name="uq_account_persons_id_account"),
        # The media layer reuses the asset for an identical upload in the same account.
        sa.UniqueConstraint(
            "account_id",
            "source_person_asset_id",
            name="uq_account_persons_source_asset",
        ),
    )
    op.create_index(
        "ix_account_persons_demographics",
        "account_persons",
        ["account_id", "gender", "age_range"],
    )

    op.create_table(
        "person_tryon_observations",
        sa.Column(
            "observation_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("person_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("render_job_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("business_account_id", UUID),
        sa.Column("store_id", UUID),
        sa.Column("observed_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(tenant_id IS NULL AND business_account_id IS NULL AND store_id IS NULL) OR "
            "(tenant_id IS NOT NULL AND business_account_id IS NOT NULL)",
            name="ck_person_observations_business_scope",
        ),
        sa.ForeignKeyConstraint(
            ["person_id", "account_id"],
            ["account_persons.person_id", "account_persons.account_id"],
            name="fk_person_observations_person_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["render_job_id", "account_id"],
            ["render_jobs.job_id", "render_jobs.account_id"],
            name="fk_person_observations_job_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_person_observations_tenant_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["store_id", "business_account_id"],
            ["business_stores.store_id", "business_stores.account_id"],
            name="fk_person_observations_store_account",
        ),
        sa.UniqueConstraint("render_job_id", name="uq_person_observations_render_job"),
    )
    op.create_index(
        "ix_person_observations_business_store",
        "person_tryon_observations",
        ["business_account_id", "tenant_id", "store_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_observations_business_store", table_name="person_tryon_observations")
    op.drop_table("person_tryon_observations")
    op.drop_index("ix_account_persons_demographics", table_name="account_persons")
    op.drop_table("account_persons")
