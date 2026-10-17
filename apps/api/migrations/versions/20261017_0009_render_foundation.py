"""Add render quotes, canonical jobs, attempts, results, and guarded transitions.

Revision ID: 20261017_0009
Revises: 20261017_0008
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0009"
down_revision: str | None = "20261017_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "render_quotes": {"classification": "private", "owner_columns": ["account_id", "tenant_id"]},
    "render_jobs": {"classification": "private", "owner_columns": ["account_id", "tenant_id"]},
    "render_attempts": {"classification": "private", "owner_columns": ["account_id", "tenant_id"]},
    "render_results": {"classification": "private", "owner_columns": ["account_id", "tenant_id"]},
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_consent_records_id_account", "consent_records", ["consent_id", "account_id"]
    )
    op.create_unique_constraint(
        "uq_ledger_entries_id_account", "ledger_entries", ["entry_id", "account_id"]
    )
    op.create_table(
        "render_quotes",
        sa.Column("quote_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("store_session_id", UUID),
        sa.Column("catalog_item_id", UUID, nullable=False),
        sa.Column("person_asset_id", UUID, nullable=False),
        sa.Column("consent_id", UUID, nullable=False),
        sa.Column("price_version_id", UUID, nullable=False),
        sa.Column("token_cost", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("token_cost > 0", name="ck_render_quotes_positive_cost"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'USED', 'EXPIRED')", name="ck_render_quotes_status"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_render_quotes_expiry"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_render_quotes_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_render_quotes_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["store_session_id", "tenant_id", "account_id"],
            [
                "guest_store_sessions.store_session_id",
                "guest_store_sessions.tenant_id",
                "guest_store_sessions.account_id",
            ],
            name="fk_render_quotes_store_session_scope",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"], ["catalog_items.item_id"], name="fk_render_quotes_item"
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "person_asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_render_quotes_person_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["consent_id", "account_id"],
            ["consent_records.consent_id", "consent_records.account_id"],
            name="fk_render_quotes_consent_account",
        ),
        sa.ForeignKeyConstraint(
            ["price_version_id"], ["price_versions.price_version_id"], name="fk_render_quotes_price"
        ),
        sa.UniqueConstraint("quote_id", "account_id", name="uq_render_quotes_id_account"),
    )

    op.create_table(
        "render_jobs",
        sa.Column("job_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("quote_id", UUID, nullable=False),
        sa.Column("hold_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'DELIVERED', 'FAILED', 'CANCELLED')",
            name="ck_render_jobs_status",
        ),
        sa.CheckConstraint(
            "(status IN ('FAILED', 'CANCELLED') AND error_code IS NOT NULL) OR "
            "(status NOT IN ('FAILED', 'CANCELLED') AND error_code IS NULL)",
            name="ck_render_jobs_error_code",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id", "account_id"],
            ["render_quotes.quote_id", "render_quotes.account_id"],
            name="fk_render_jobs_quote_account",
        ),
        sa.ForeignKeyConstraint(
            ["hold_id", "account_id"],
            ["wallet_holds.hold_id", "wallet_holds.account_id"],
            name="fk_render_jobs_hold_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_render_jobs_tenant_account",
        ),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_render_jobs_account_key"),
        sa.UniqueConstraint("quote_id", name="uq_render_jobs_quote"),
        sa.UniqueConstraint("job_id", "account_id", name="uq_render_jobs_id_account"),
    )
    op.create_index("ix_render_jobs_owner_time", "render_jobs", ["account_id", "created_at"])
    op.execute(
        """
        CREATE FUNCTION enforce_render_job_transition() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = NEW.status THEN RETURN NEW; END IF;
            IF NOT (
                (OLD.status = 'PENDING' AND NEW.status IN ('PROCESSING', 'FAILED', 'CANCELLED')) OR
                (OLD.status = 'PROCESSING' AND NEW.status IN ('DELIVERED', 'FAILED', 'CANCELLED'))
            ) THEN RAISE EXCEPTION 'illegal render job transition: % -> %', OLD.status, NEW.status;
            END IF;
            RETURN NEW;
        END; $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_render_job_transition BEFORE UPDATE OF status ON render_jobs
        FOR EACH ROW EXECUTE FUNCTION enforce_render_job_transition()"""
    )

    op.create_table(
        "render_attempts",
        sa.Column(
            "attempt_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False),
        sa.Column("provider_attempt_ref", sa.String(120)),
        sa.Column("model_version", sa.String(120), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_cost_minor", sa.BigInteger()),
        sa.Column("started_at", TIMESTAMP, nullable=False),
        sa.Column("finished_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("attempt_number > 0", name="ck_render_attempts_number"),
        sa.CheckConstraint(
            "status IN ('STARTED', 'SUCCEEDED', 'FAILED', 'TIMED_OUT')",
            name="ck_render_attempts_status",
        ),
        sa.CheckConstraint(
            "provider_cost_minor IS NULL OR provider_cost_minor >= 0",
            name="ck_render_attempts_cost",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "account_id"],
            ["render_jobs.job_id", "render_jobs.account_id"],
            name="fk_render_attempts_job_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_render_attempts_tenant_account",
        ),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_render_attempts_job_number"),
        sa.UniqueConstraint("provider_attempt_ref", name="uq_render_attempts_provider_ref"),
    )

    op.create_table(
        "render_results",
        sa.Column("result_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("result_asset_id", UUID, nullable=False),
        sa.Column("source_person_asset_id", UUID, nullable=False),
        sa.Column("catalog_item_id", UUID, nullable=False),
        sa.Column("model_version", sa.String(120), nullable=False),
        sa.Column("quality_state", sa.String(24), nullable=False),
        sa.Column("quality_details", postgresql.JSONB(), nullable=False),
        sa.Column("ledger_entry_id", UUID),
        sa.Column("disclosure_version", sa.String(40), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "quality_state IN ('APPROVED', 'REJECTED')", name="ck_render_results_quality"
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "account_id"],
            ["render_jobs.job_id", "render_jobs.account_id"],
            name="fk_render_results_job_account",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "result_asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_render_results_result_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "source_person_asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_render_results_source_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"], ["catalog_items.item_id"], name="fk_render_results_item"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_entry_id", "account_id"],
            ["ledger_entries.entry_id", "ledger_entries.account_id"],
            name="fk_render_results_ledger_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_render_results_tenant_account",
        ),
        sa.UniqueConstraint("job_id", name="uq_render_results_job"),
    )


def downgrade() -> None:
    op.drop_table("render_results")
    op.drop_table("render_attempts")
    op.execute("DROP TRIGGER trg_render_job_transition ON render_jobs")
    op.execute("DROP FUNCTION enforce_render_job_transition()")
    op.drop_index("ix_render_jobs_owner_time", table_name="render_jobs")
    op.drop_table("render_jobs")
    op.drop_table("render_quotes")
    op.drop_constraint("uq_ledger_entries_id_account", "ledger_entries", type_="unique")
    op.drop_constraint("uq_consent_records_id_account", "consent_records", type_="unique")
