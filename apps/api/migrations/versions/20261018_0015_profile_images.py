"""Add multiple reusable photos to person profiles.

Revision ID: 20261018_0015
Revises: 20261017_0014
Created: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261018_0015"
down_revision: str | None = "20261017_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "person_profile_images": {"classification": "private", "owner_columns": ["account_id"]},
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "person_profile_images",
        sa.Column(
            "profile_image_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("profile_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("asset_id", UUID, nullable=False),
        sa.Column("consent_id", UUID, nullable=False),
        sa.Column("photo_type", sa.String(24), nullable=False),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "photo_type IN ('FULL_BODY', 'CLOSE_UP', 'OTHER')",
            name="ck_person_profile_images_type",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["person_profiles.profile_id"],
            name="fk_person_profile_images_profile",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_person_profile_images_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["consent_id"],
            ["consent_records.consent_id"],
            name="fk_person_profile_images_consent",
        ),
        sa.UniqueConstraint("profile_id", "asset_id", name="uq_person_profile_images_asset"),
        sa.UniqueConstraint("profile_id", "photo_type", name="uq_person_profile_images_type"),
    )
    op.create_index(
        "uq_person_profile_images_primary",
        "person_profile_images",
        ["profile_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_index(
        "ix_person_profile_images_account",
        "person_profile_images",
        ["account_id", "profile_id"],
    )
    op.execute(
        """
        INSERT INTO person_profile_images
            (profile_id, account_id, asset_id, consent_id, photo_type, label, is_primary)
        SELECT
            profile_id,
            account_id,
            person_asset_id,
            consent_id,
            'FULL_BODY',
            'Full body',
            true
        FROM person_profiles
        """
    )


def downgrade() -> None:
    op.drop_index("ix_person_profile_images_account", table_name="person_profile_images")
    op.drop_index("uq_person_profile_images_primary", table_name="person_profile_images")
    op.drop_table("person_profile_images")
