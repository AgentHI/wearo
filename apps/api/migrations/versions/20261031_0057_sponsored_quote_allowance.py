"""Allow business-sponsored quote allowances above the beta personal limit.

Revision ID: 20261031_0057
Revises: 20261031_0056
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0057"
down_revision: str | None = "20261031_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_render_quotes_beta_allowance", "render_quotes", type_="check")
    op.alter_column(
        "render_quotes",
        "remaining_allowance",
        existing_type=sa.SmallInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_render_quotes_beta_allowance",
        "render_quotes",
        "remaining_allowance IS NULL OR remaining_allowance >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_render_quotes_beta_allowance", "render_quotes", type_="check")
    op.execute("""UPDATE render_quotes
        SET remaining_allowance=3
        WHERE remaining_allowance > 3""")
    op.alter_column(
        "render_quotes",
        "remaining_allowance",
        existing_type=sa.Integer(),
        type_=sa.SmallInteger(),
        existing_nullable=True,
        postgresql_using="remaining_allowance::smallint",
    )
    op.create_check_constraint(
        "ck_render_quotes_beta_allowance",
        "render_quotes",
        "remaining_allowance IS NULL OR remaining_allowance BETWEEN 1 AND 3",
    )
