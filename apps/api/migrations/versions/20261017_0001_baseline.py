"""Establish the empty Wearo migration baseline.

Revision ID: 20261017_0001
Revises: None
Created: 2026-10-17
"""

from collections.abc import Sequence

revision: str = "20261017_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    """Create no product tables until their owning task is approved."""


def downgrade() -> None:
    """Return to the pre-baseline state."""
