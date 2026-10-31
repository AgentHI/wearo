"""Select one database model for new try-on generations.

Revision ID: 20261031_0051
Revises: 20261031_0050
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0051"
down_revision: str | None = "20261031_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "ai_models",
        sa.Column("selected_for_tryon", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_ai_models_selected_tryon",
        "ai_models",
        ["selected_for_tryon"],
        unique=True,
        postgresql_where=sa.text("selected_for_tryon"),
    )


def downgrade() -> None:
    op.drop_index("uq_ai_models_selected_tryon", table_name="ai_models")
    op.drop_column("ai_models", "selected_for_tryon")
