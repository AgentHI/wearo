from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from apps.api.wearo_api.database import normalize_database_url

pytestmark = pytest.mark.integration


@pytest.fixture
def connection() -> Iterator[Connection]:
    raw_url = os.environ.get("WEARO_DATABASE_URL")
    if raw_url is None:
        pytest.skip("WEARO_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(normalize_database_url(raw_url))
    with engine.connect() as database_connection:
        transaction = database_connection.begin()
        yield database_connection
        transaction.rollback()
    engine.dispose()


def create_wallet(connection: Connection) -> tuple[str, str, str]:
    account_id = str(uuid4())
    wallet_id = str(uuid4())
    bucket_id = str(uuid4())
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:id, 'CONSUMER')"),
        {"id": account_id},
    )
    connection.execute(
        text("INSERT INTO wallets (wallet_id, account_id) VALUES (:wallet, :account)"),
        {"wallet": wallet_id, "account": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO wallet_buckets (bucket_id, account_id, wallet_id, bucket_type) "
            "VALUES (:bucket, :account, :wallet, 'PURCHASED')"
        ),
        {"bucket": bucket_id, "account": account_id, "wallet": wallet_id},
    )
    return account_id, wallet_id, bucket_id


def test_account_has_only_one_wallet(connection: Connection) -> None:
    account_id, _, _ = create_wallet(connection)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text("INSERT INTO wallets (account_id) VALUES (:account)"),
            {"account": account_id},
        )


def test_ledger_rejects_cross_account_bucket(connection: Connection) -> None:
    first_account, first_wallet, _ = create_wallet(connection)
    _, _, foreign_bucket = create_wallet(connection)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO ledger_entries "
                "(account_id, wallet_id, bucket_id, entry_type, amount, operation_key) "
                "VALUES (:account, :wallet, :bucket, 'CREDIT', 10, 'cross-account')"
            ),
            {"account": first_account, "wallet": first_wallet, "bucket": foreign_bucket},
        )


def test_ledger_is_append_only(connection: Connection) -> None:
    account_id, wallet_id, bucket_id = create_wallet(connection)
    entry_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO ledger_entries "
            "(entry_id, account_id, wallet_id, bucket_id, entry_type, amount, operation_key) "
            "VALUES (:entry, :account, :wallet, :bucket, 'CREDIT', 10, 'credit-1')"
        ),
        {"entry": entry_id, "account": account_id, "wallet": wallet_id, "bucket": bucket_id},
    )
    with pytest.raises(DBAPIError, match="append-only"), connection.begin_nested():
        connection.execute(
            text("UPDATE ledger_entries SET amount = 20 WHERE entry_id = :entry"),
            {"entry": entry_id},
        )


def test_payment_provider_event_is_globally_unique(connection: Connection) -> None:
    account_id, _, _ = create_wallet(connection)
    pack_id = str(uuid4())
    order_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO token_packs "
            "(pack_id, code, purchased_tokens, amount_minor, currency, effective_from) "
            "VALUES (:pack, 'TEST-PACK', 10, 100, 'INR', now())"
        ),
        {"pack": pack_id},
    )
    connection.execute(
        text(
            "INSERT INTO payment_orders "
            "(payment_order_id, account_id, pack_id, idempotency_key, amount_minor, currency) "
            "VALUES (:order, :account, :pack, 'order-1', 100, 'INR')"
        ),
        {"order": order_id, "account": account_id, "pack": pack_id},
    )
    statement = text(
        "INSERT INTO payment_events "
        "(account_id, payment_order_id, provider_event_id, event_type, received_at) "
        "VALUES (:account, :order, 'provider-event-1', 'CONFIRMED', now())"
    )
    connection.execute(statement, {"account": account_id, "order": order_id})
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(statement, {"account": account_id, "order": order_id})
