"""Add isolated wallets, immutable ledger records, and payment foundations.

Revision ID: 20261017_0005
Revises: 20261017_0004
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0005"
down_revision: str | None = "20261017_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "wallets": {"classification": "financial", "owner_columns": ["account_id"]},
    "wallet_buckets": {"classification": "financial", "owner_columns": ["account_id"]},
    "price_versions": {"classification": "public", "owner_columns": []},
    "token_packs": {"classification": "public", "owner_columns": []},
    "wallet_holds": {"classification": "financial", "owner_columns": ["account_id"]},
    "ledger_entries": {"classification": "financial", "owner_columns": ["account_id"]},
    "payment_orders": {"classification": "financial", "owner_columns": ["account_id"]},
    "payment_events": {"classification": "financial", "owner_columns": ["account_id"]},
    "invoices": {"classification": "financial", "owner_columns": ["account_id"]},
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "wallets",
        sa.Column("wallet_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("unit", sa.String(24), nullable=False, server_default="WEARO_TOKEN"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("unit = 'WEARO_TOKEN'", name="ck_wallets_unit"),
        sa.CheckConstraint("version >= 0", name="ck_wallets_version"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"], name="fk_wallets_account"),
        sa.UniqueConstraint("account_id", name="uq_wallets_account"),
        sa.UniqueConstraint("wallet_id", "account_id", name="uq_wallets_id_account"),
    )

    op.create_table(
        "wallet_buckets",
        sa.Column("bucket_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("wallet_id", UUID, nullable=False),
        sa.Column("bucket_type", sa.String(16), nullable=False),
        sa.Column("expires_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("bucket_type IN ('PURCHASED', 'PROMO')", name="ck_wallet_buckets_type"),
        sa.CheckConstraint(
            "bucket_type = 'PROMO' OR expires_at IS NULL", name="ck_wallet_buckets_expiry"
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id", "account_id"],
            ["wallets.wallet_id", "wallets.account_id"],
            name="fk_wallet_buckets_wallet_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("bucket_id", "account_id", name="uq_wallet_buckets_id_account"),
    )
    op.create_index(
        "uq_wallet_buckets_purchased",
        "wallet_buckets",
        ["wallet_id"],
        unique=True,
        postgresql_where=sa.text("bucket_type = 'PURCHASED'"),
    )

    op.create_table(
        "price_versions",
        sa.Column(
            "price_version_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("action_code", sa.String(40), nullable=False),
        sa.Column("token_cost", sa.BigInteger(), nullable=False),
        sa.Column("effective_from", TIMESTAMP, nullable=False),
        sa.Column("effective_until", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("token_cost > 0", name="ck_price_versions_positive_cost"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_price_versions_window",
        ),
        sa.UniqueConstraint("action_code", "effective_from", name="uq_price_versions_action_from"),
    )

    op.create_table(
        "token_packs",
        sa.Column("pack_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("purchased_tokens", sa.BigInteger(), nullable=False),
        sa.Column("promo_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("effective_from", TIMESTAMP, nullable=False),
        sa.Column("effective_until", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("purchased_tokens > 0", name="ck_token_packs_purchased_positive"),
        sa.CheckConstraint("promo_tokens >= 0", name="ck_token_packs_promo_nonnegative"),
        sa.CheckConstraint("amount_minor > 0", name="ck_token_packs_amount_positive"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_token_packs_currency"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_token_packs_window",
        ),
        sa.UniqueConstraint("code", "effective_from", name="uq_token_packs_code_from"),
    )

    op.create_table(
        "wallet_holds",
        sa.Column("hold_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("wallet_id", UUID, nullable=False),
        sa.Column("price_version_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("settled_at", TIMESTAMP),
        sa.Column("released_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_wallet_holds_positive_amount"),
        sa.CheckConstraint(
            "state IN ('ACTIVE', 'SETTLED', 'RELEASED', 'EXPIRED')", name="ck_wallet_holds_state"
        ),
        sa.CheckConstraint(
            "(state = 'SETTLED' AND settled_at IS NOT NULL AND released_at IS NULL) OR "
            "(state IN ('RELEASED', 'EXPIRED') AND released_at IS NOT NULL "
            "AND settled_at IS NULL) OR "
            "(state = 'ACTIVE' AND settled_at IS NULL AND released_at IS NULL)",
            name="ck_wallet_holds_terminal_time",
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id", "account_id"],
            ["wallets.wallet_id", "wallets.account_id"],
            name="fk_wallet_holds_wallet_account",
        ),
        sa.ForeignKeyConstraint(
            ["price_version_id"], ["price_versions.price_version_id"], name="fk_wallet_holds_price"
        ),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_wallet_holds_account_key"),
        sa.UniqueConstraint("hold_id", "account_id", name="uq_wallet_holds_id_account"),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("entry_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("wallet_id", UUID, nullable=False),
        sa.Column("bucket_id", UUID, nullable=False),
        sa.Column("hold_id", UUID),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("operation_key", sa.String(100), nullable=False),
        sa.Column("performed_by_principal_id", UUID),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount <> 0", name="ck_ledger_entries_nonzero"),
        sa.CheckConstraint(
            "entry_type IN ('CREDIT', 'DEBIT', 'HOLD', 'RELEASE', 'RECREDIT', 'EXPIRY')",
            name="ck_ledger_entries_type",
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id", "account_id"],
            ["wallets.wallet_id", "wallets.account_id"],
            name="fk_ledger_entries_wallet_account",
        ),
        sa.ForeignKeyConstraint(
            ["bucket_id", "account_id"],
            ["wallet_buckets.bucket_id", "wallet_buckets.account_id"],
            name="fk_ledger_entries_bucket_account",
        ),
        sa.ForeignKeyConstraint(
            ["hold_id", "account_id"],
            ["wallet_holds.hold_id", "wallet_holds.account_id"],
            name="fk_ledger_entries_hold_account",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by_principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_ledger_entries_actor_account",
        ),
        sa.UniqueConstraint(
            "account_id", "operation_key", "entry_type", name="uq_ledger_entries_operation_type"
        ),
    )
    op.create_index("ix_ledger_entries_wallet_time", "ledger_entries", ["wallet_id", "created_at"])
    op.execute(
        """CREATE FUNCTION reject_ledger_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'ledger entries are append-only'; END; $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_ledger_entries_append_only BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION reject_ledger_mutation()"""
    )

    op.create_table(
        "payment_orders",
        sa.Column(
            "payment_order_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("pack_id", UUID, nullable=False),
        sa.Column("provider_order_id", sa.String(120)),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="CREATED"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_minor > 0", name="ck_payment_orders_amount_positive"),
        sa.CheckConstraint(
            "state IN ('CREATED', 'PENDING', 'CONFIRMED', 'FAILED', 'REFUNDED')",
            name="ck_payment_orders_state",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_payment_orders_account"
        ),
        sa.ForeignKeyConstraint(
            ["pack_id"], ["token_packs.pack_id"], name="fk_payment_orders_pack"
        ),
        sa.UniqueConstraint("provider_order_id", name="uq_payment_orders_provider_order"),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_payment_orders_account_key"),
        sa.UniqueConstraint("payment_order_id", "account_id", name="uq_payment_orders_id_account"),
    )

    op.create_table(
        "payment_events",
        sa.Column(
            "payment_event_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("payment_order_id", UUID, nullable=False),
        sa.Column("provider_event_id", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("received_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["payment_order_id", "account_id"],
            ["payment_orders.payment_order_id", "payment_orders.account_id"],
            name="fk_payment_events_order_account",
        ),
        sa.UniqueConstraint("provider_event_id", name="uq_payment_events_provider_event"),
    )

    op.create_table(
        "invoices",
        sa.Column(
            "invoice_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("payment_order_id", UUID, nullable=False),
        sa.Column("invoice_number", sa.String(80), nullable=False),
        sa.Column("issued_at", TIMESTAMP, nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_minor > 0", name="ck_invoices_amount_positive"),
        sa.ForeignKeyConstraint(
            ["payment_order_id", "account_id"],
            ["payment_orders.payment_order_id", "payment_orders.account_id"],
            name="fk_invoices_order_account",
        ),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_number"),
        sa.UniqueConstraint("payment_order_id", name="uq_invoices_payment_order"),
    )


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_table("payment_events")
    op.drop_table("payment_orders")
    op.execute("DROP TRIGGER trg_ledger_entries_append_only ON ledger_entries")
    op.execute("DROP FUNCTION reject_ledger_mutation()")
    op.drop_index("ix_ledger_entries_wallet_time", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("wallet_holds")
    op.drop_table("token_packs")
    op.drop_table("price_versions")
    op.drop_index("uq_wallet_buckets_purchased", table_name="wallet_buckets")
    op.drop_table("wallet_buckets")
    op.drop_table("wallets")
