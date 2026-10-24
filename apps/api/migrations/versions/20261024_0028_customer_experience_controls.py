"""Add tenant-controlled retention and profile deletion windows.

Revision ID: 20261024_0028
Revises: 20261023_0027
Created: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0028"
down_revision: str | None = "20261023_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "business_profiles",
        sa.Column("image_retention_days", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "business_profiles",
        sa.Column("profile_deletion_hours", sa.Integer(), nullable=False, server_default="24"),
    )
    op.create_check_constraint(
        "ck_business_profiles_image_retention_days",
        "business_profiles",
        "image_retention_days BETWEEN 1 AND 30",
    )
    op.create_check_constraint(
        "ck_business_profiles_profile_deletion_hours",
        "business_profiles",
        "profile_deletion_hours BETWEEN 1 AND 24",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_business_profiles_profile_deletion_hours", "business_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_business_profiles_image_retention_days", "business_profiles", type_="check"
    )
    op.drop_column("business_profiles", "profile_deletion_hours")
    op.drop_column("business_profiles", "image_retention_days")
