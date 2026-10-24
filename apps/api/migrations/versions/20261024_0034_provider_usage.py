"""Store provider-reported usage for successful renders.

Revision ID: 20261024_0034
Revises: 20261024_0033
Created: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0034"
down_revision: str | None = "20261024_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column("render_results", sa.Column("provider_usage", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("render_results", "provider_usage")
