"""Widen reusable profile status for DELETION_REQUESTED.

Revision ID: 20261017_0014
Revises: 20261017_0013
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261017_0014"
down_revision: str | None = "20261017_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.alter_column(
        "person_profiles",
        "status",
        existing_type=sa.String(16),
        type_=sa.String(24),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "person_profiles",
        "status",
        existing_type=sa.String(24),
        type_=sa.String(16),
        existing_nullable=False,
    )
