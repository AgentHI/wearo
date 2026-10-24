"""Allow up to ten reusable photos per person profile.

Revision ID: 20261024_0036
Revises: 20261024_0035
Created: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261024_0036"
down_revision: str | None = "20261024_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_person_profile_images_type", "person_profile_images", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_person_profile_images_type",
        "person_profile_images",
        ["profile_id", "photo_type"],
    )
