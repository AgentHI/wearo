"""Add effective-dated platform pricing settings.

Revision ID: 20261026_0046
Revises: 20261026_0045
Created: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261026_0046"
down_revision: str | None = "20261026_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "platform_pricing_settings": {"classification": "public", "owner_columns": []}
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "platform_pricing_settings",
        sa.Column(
            "pricing_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("plan_code", sa.String(40), nullable=False),
        sa.Column("business_type", sa.String(32)),
        sa.Column("monthly_fee_minor", sa.BigInteger(), nullable=False),
        sa.Column("try_on_token_cost", sa.BigInteger(), nullable=False),
        sa.Column("free_trial_tokens", sa.BigInteger(), nullable=False),
        sa.Column("trial_duration_days", sa.Integer(), nullable=False),
        sa.Column("payment_grace_days", sa.Integer(), nullable=False),
        sa.Column("gst_basis_points", sa.Integer(), nullable=False),
        sa.Column("effective_from", TIMESTAMP, nullable=False),
        sa.Column("effective_until", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("monthly_fee_minor >= 0", name="ck_platform_pricing_monthly_fee"),
        sa.CheckConstraint("try_on_token_cost > 0", name="ck_platform_pricing_tryon_cost"),
        sa.CheckConstraint("free_trial_tokens >= 0", name="ck_platform_pricing_trial_tokens"),
        sa.CheckConstraint(
            "trial_duration_days BETWEEN 1 AND 365", name="ck_platform_pricing_trial_days"
        ),
        sa.CheckConstraint(
            "payment_grace_days BETWEEN 0 AND 90", name="ck_platform_pricing_grace_days"
        ),
        sa.CheckConstraint("gst_basis_points BETWEEN 0 AND 10000", name="ck_platform_pricing_gst"),
        sa.CheckConstraint(
            "business_type IS NULL OR business_type IN ('BOUTIQUE', 'CLOTHING_RETAILER', "
            "'JEWELLERY_RETAILER', 'ENTERPRISE_CHAIN', 'OTHER')",
            name="ck_platform_pricing_business_type",
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_platform_pricing_window",
        ),
        sa.UniqueConstraint(
            "plan_code", "business_type", "effective_from", name="uq_platform_pricing_version"
        ),
    )
    op.add_column("token_packs", sa.Column("business_type", sa.String(32)))
    op.add_column(
        "token_packs",
        sa.Column("discount_basis_points", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_token_packs_discount",
        "token_packs",
        "discount_basis_points BETWEEN 0 AND 10000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_token_packs_discount", "token_packs", type_="check")
    op.drop_column("token_packs", "discount_basis_points")
    op.drop_column("token_packs", "business_type")
    op.drop_table("platform_pricing_settings")
