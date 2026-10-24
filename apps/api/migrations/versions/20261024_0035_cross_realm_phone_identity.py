"""Allow one destination to identify consumer and business principals.

Revision ID: 20261024_0035
Revises: 20261024_0034
Created: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261024_0035"
down_revision: str | None = "20261024_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_principal_identities_channel_value", "principal_identities", type_="unique"
    )
    op.create_unique_constraint(
        "uq_principal_identities_account_channel_value",
        "principal_identities",
        ["account_id", "channel", "normalized_value"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_principal_identities_account_channel_value",
        "principal_identities",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_principal_identities_channel_value",
        "principal_identities",
        ["channel", "normalized_value"],
    )
