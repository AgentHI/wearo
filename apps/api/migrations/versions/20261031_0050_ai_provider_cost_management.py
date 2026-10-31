"""Add provider funding and model-level usage cost management.

Revision ID: 20261031_0050
Revises: 20261028_0049
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261031_0050"
down_revision: str | None = "20261028_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "ai_providers": {"classification": "internal", "owner_columns": []},
    "ai_models": {"classification": "internal", "owner_columns": []},
    "provider_purchases": {"classification": "financial", "owner_columns": []},
    "model_usage_costs": {"classification": "financial", "owner_columns": []},
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column(
            "provider_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("adapter_type", sa.String(40), nullable=False),
        sa.Column("credential_env_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISABLED','ARCHIVED')", name="ck_ai_providers_status"
        ),
        sa.CheckConstraint(
            "credential_env_name ~ '^WEARO_[A-Z0-9_]+$'", name="ck_ai_providers_env"
        ),
    )
    op.create_table(
        "ai_models",
        sa.Column("model_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider_id", UUID, nullable=False),
        sa.Column("api_model_id", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("capability", sa.String(40), nullable=False, server_default="TRY_ON"),
        sa.Column("region", sa.String(80), nullable=False, server_default="global"),
        sa.Column("billing_method", sa.String(24), nullable=False),
        sa.Column(
            "input_unit_price_usd_micros", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "output_unit_price_usd_micros", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("request_price_usd_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("fallback_cost_usd_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.provider_id"]),
        sa.UniqueConstraint("provider_id", "api_model_id", "region", name="uq_ai_models_route"),
        sa.CheckConstraint(
            "billing_method IN ('TOKEN','REQUEST','IMAGE','CREDIT')", name="ck_ai_models_billing"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISABLED','ARCHIVED')", name="ck_ai_models_status"
        ),
        sa.CheckConstraint(
            "input_unit_price_usd_micros >= 0 AND output_unit_price_usd_micros >= 0 "
            "AND request_price_usd_micros >= 0 AND fallback_cost_usd_micros >= 0",
            name="ck_ai_models_prices",
        ),
    )
    op.create_table(
        "provider_purchases",
        sa.Column(
            "purchase_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("provider_id", UUID, nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("units_purchased", sa.Numeric(24, 6)),
        sa.Column("unit_type", sa.String(16), nullable=False),
        sa.Column("reference", sa.String(160)),
        sa.Column("purchased_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.provider_id"]),
        sa.CheckConstraint("amount_minor > 0", name="ck_provider_purchases_amount"),
        sa.CheckConstraint(
            "units_purchased IS NULL OR units_purchased > 0", name="ck_provider_purchases_units"
        ),
        sa.CheckConstraint(
            "unit_type IN ('USD','TOKEN','IMAGE','CREDIT')", name="ck_provider_purchases_unit"
        ),
    )
    op.create_table(
        "model_usage_costs",
        sa.Column(
            "usage_cost_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("job_id", UUID, nullable=False, unique=True),
        sa.Column("model_id", UUID, nullable=False),
        sa.Column("input_units", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_units", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd_micros", sa.BigInteger(), nullable=False),
        sa.Column("cost_basis", sa.String(16), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["render_jobs.job_id"]),
        sa.ForeignKeyConstraint(["model_id"], ["ai_models.model_id"]),
        sa.CheckConstraint("cost_usd_micros >= 0", name="ck_model_usage_cost"),
        sa.CheckConstraint(
            "cost_basis IN ('ACTUAL','CALCULATED','ESTIMATED')", name="ck_model_usage_basis"
        ),
    )
    op.create_index(
        "ix_model_usage_costs_model_time", "model_usage_costs", ["model_id", "created_at"]
    )
    op.create_index("ix_render_jobs_created_global", "render_jobs", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_render_jobs_created_global", table_name="render_jobs")
    op.drop_index("ix_model_usage_costs_model_time", table_name="model_usage_costs")
    op.drop_table("model_usage_costs")
    op.drop_table("provider_purchases")
    op.drop_table("ai_models")
    op.drop_table("ai_providers")
