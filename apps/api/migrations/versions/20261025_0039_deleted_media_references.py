"""Remove storage references from permanently deleted media.

Revision ID: 20261025_0039
Revises: 20261025_0038
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0039"
down_revision: str | None = "20261025_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.alter_column(
        "media_assets",
        "object_key",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.execute("UPDATE media_assets SET object_key = NULL WHERE deletion_state = 'DELETED'")
    op.create_check_constraint(
        "ck_media_assets_deleted_object_key",
        "media_assets",
        "(deletion_state = 'DELETED' AND object_key IS NULL) OR "
        "(deletion_state <> 'DELETED' AND object_key IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_media_assets_deleted_object_key", "media_assets", type_="check")
    op.execute(
        "UPDATE media_assets SET object_key = 'deleted/' || asset_id::text WHERE object_key IS NULL"
    )
    op.alter_column(
        "media_assets",
        "object_key",
        existing_type=sa.Text(),
        nullable=False,
    )
