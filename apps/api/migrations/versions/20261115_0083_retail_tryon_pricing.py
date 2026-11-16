"""Add separately published retail try-on pricing.

Revision ID: 20261115_0083
Revises: 20261114_0082
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261115_0083"
down_revision: str | None = "20261114_0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retail_tryon_prices",
        sa.Column(
            "retail_price_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("tokens_per_tryon", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price_minor > 0", name="ck_retail_tryon_price_positive"),
        sa.CheckConstraint("price_minor % 20 = 0", name="ck_retail_tryon_price_token_increment"),
        sa.CheckConstraint("tokens_per_tryon = price_minor / 20", name="ck_retail_tryon_price_formula"),
        sa.CheckConstraint("currency = 'INR'", name="ck_retail_tryon_price_currency"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_retail_tryon_price_window",
        ),
    )
    op.create_index(
        "uq_retail_tryon_price_active",
        "retail_tryon_prices",
        ["currency"],
        unique=True,
        postgresql_where=sa.text("effective_until IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_retail_tryon_price_active", table_name="retail_tryon_prices")
    op.drop_table("retail_tryon_prices")
