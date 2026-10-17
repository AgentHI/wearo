"""Add reusable beta person profiles and daily generation quota.

Revision ID: 20261017_0010
Revises: 20261017_0009
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0010"
down_revision: str | None = "20261017_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "person_profiles": {"classification": "private", "owner_columns": ["account_id"]},
    "generation_daily_usage": {
        "classification": "private",
        "owner_columns": ["account_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "person_profiles",
        sa.Column(
            "profile_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("person_asset_id", UUID, nullable=False),
        sa.Column("consent_id", UUID, nullable=False),
        sa.Column("height_cm", sa.Numeric(5, 1)),
        sa.Column("weight_kg", sa.Numeric(5, 1)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("last_used_at", TIMESTAMP),
        sa.Column("delete_after", TIMESTAMP),
        sa.Column("deleted_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "height_cm IS NULL OR height_cm BETWEEN 80 AND 260", name="ck_person_profiles_height"
        ),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg BETWEEN 20 AND 350", name="ck_person_profiles_weight"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DELETION_REQUESTED', 'DELETED')",
            name="ck_person_profiles_status",
        ),
        sa.CheckConstraint(
            "(status = 'DELETED') = (deleted_at IS NOT NULL)", name="ck_person_profiles_deleted_at"
        ),
        sa.ForeignKeyConstraint(
            ["principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_person_profiles_principal_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "person_asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_person_profiles_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["consent_id"], ["consent_records.consent_id"], name="fk_person_profiles_consent"
        ),
    )
    op.create_index(
        "uq_person_profiles_active_account",
        "person_profiles",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index("ix_person_profiles_retention", "person_profiles", ["status", "delete_after"])

    op.create_table(
        "generation_daily_usage",
        sa.Column("usage_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("usage_date_ist", sa.Date(), nullable=False),
        sa.Column("successful_generations", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("active_job_id", UUID),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "successful_generations BETWEEN 0 AND 3", name="ck_generation_daily_usage_limit"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_generation_daily_usage_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["active_job_id"], ["render_jobs.job_id"], name="fk_generation_daily_usage_active_job"
        ),
        sa.UniqueConstraint(
            "account_id", "usage_date_ist", name="uq_generation_daily_usage_account_date"
        ),
    )


def downgrade() -> None:
    op.drop_table("generation_daily_usage")
    op.drop_index("ix_person_profiles_retention", table_name="person_profiles")
    op.drop_index("uq_person_profiles_active_account", table_name="person_profiles")
    op.drop_table("person_profiles")
