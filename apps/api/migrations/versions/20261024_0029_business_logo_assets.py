"""Allow permanent business logo media assets.

Revision ID: 20261024_0029
Revises: 20261024_0028
Created: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261024_0029"
down_revision: str | None = "20261024_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PERSON_SOURCE', 'PRODUCT_SOURCE', 'RENDER_RESULT', 'BUSINESS_LOGO')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_media_assets_purpose", "media_assets", type_="check")
    op.create_check_constraint(
        "ck_media_assets_purpose",
        "media_assets",
        "purpose IN ('PERSON_SOURCE', 'PRODUCT_SOURCE', 'RENDER_RESULT')",
    )
