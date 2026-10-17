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


def create_account_asset(connection: Connection, suffix: str) -> tuple[str, str, str]:
    account_id = str(uuid4())
    principal_id = str(uuid4())
    asset_id = str(uuid4())
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:id, 'CONSUMER')"),
        {"id": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO principals "
            "(principal_id, account_id, account_kind, principal_type) "
            "VALUES (:principal, :account, 'CONSUMER', 'CONSUMER')"
        ),
        {"principal": principal_id, "account": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO media_assets "
            "(asset_id, account_id, object_key, content_hash, mime_type, purpose) "
            "VALUES (:asset, :account, :key, :hash, 'image/jpeg', 'PERSON_SOURCE')"
        ),
        {
            "asset": asset_id,
            "account": account_id,
            "key": f"private/{suffix}/{asset_id}",
            "hash": uuid4().hex,
        },
    )
    return account_id, principal_id, asset_id


def create_render_dependencies(
    connection: Connection, suffix: str
) -> tuple[str, str, str, str, str]:
    account_id, principal_id, asset_id = create_account_asset(connection, suffix)
    consent_id = str(uuid4())
    category_id = str(uuid4())
    item_id = str(uuid4())
    price_id = str(uuid4())
    wallet_id = str(uuid4())
    hold_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO consent_records "
            "(consent_id, account_id, asset_id, actor_principal_id, consent_version, purpose, "
            "permission_asserted, accepted_at) VALUES (:consent, :account, :asset, :principal, "
            "'v1', 'TRY_ON', true, now())"
        ),
        {
            "consent": consent_id,
            "account": account_id,
            "asset": asset_id,
            "principal": principal_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO offering_categories (category_id, code, offering, enabled) "
            "VALUES (:category, :code, 'SHOP', true)"
        ),
        {"category": category_id, "code": f"render-{suffix}"},
    )
    connection.execute(
        text(
            "INSERT INTO catalog_items "
            "(item_id, concept_owner, category_id, item_code, source_type, title, quality_state) "
            "VALUES (:item, 'Wearo', :category, :code, 'CONCEPT', 'Concept', 'APPROVED')"
        ),
        {"item": item_id, "category": category_id, "code": f"ITEM-{suffix}"},
    )
    connection.execute(
        text(
            "INSERT INTO price_versions "
            "(price_version_id, action_code, token_cost, effective_from) "
            "VALUES (:price, :action, 5, now())"
        ),
        {"price": price_id, "action": f"render-{suffix}"},
    )
    connection.execute(
        text("INSERT INTO wallets (wallet_id, account_id) VALUES (:wallet, :account)"),
        {"wallet": wallet_id, "account": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO wallet_holds "
            "(hold_id, account_id, wallet_id, price_version_id, idempotency_key, amount, "
            "expires_at) VALUES (:hold, :account, :wallet, :price, :key, 5, "
            "now() + interval '10 minutes')"
        ),
        {
            "hold": hold_id,
            "account": account_id,
            "wallet": wallet_id,
            "price": price_id,
            "key": f"hold-{suffix}",
        },
    )
    return account_id, asset_id, consent_id, item_id, hold_id


def create_quote_job(connection: Connection, suffix: str) -> tuple[str, str, str]:
    account_id, asset_id, consent_id, item_id, hold_id = create_render_dependencies(
        connection, suffix
    )
    price_id: object = connection.execute(
        text("SELECT price_version_id FROM wallet_holds WHERE hold_id = :hold"), {"hold": hold_id}
    ).scalar_one()
    quote_id = str(uuid4())
    job_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO render_quotes "
            "(quote_id, account_id, catalog_item_id, person_asset_id, consent_id, "
            "price_version_id, token_cost, expires_at) VALUES (:quote, :account, :item, :asset, "
            ":consent, :price, 5, now() + interval '5 minutes')"
        ),
        {
            "quote": quote_id,
            "account": account_id,
            "item": item_id,
            "asset": asset_id,
            "consent": consent_id,
            "price": price_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO render_jobs "
            "(job_id, account_id, quote_id, hold_id, idempotency_key) "
            "VALUES (:job, :account, :quote, :hold, :key)"
        ),
        {
            "job": job_id,
            "account": account_id,
            "quote": quote_id,
            "hold": hold_id,
            "key": f"render-{suffix}",
        },
    )
    return account_id, quote_id, job_id


def test_illegal_job_transition_is_rejected(connection: Connection) -> None:
    _, _, job_id = create_quote_job(connection, "transition")
    with (
        pytest.raises(DBAPIError, match="illegal render job transition"),
        connection.begin_nested(),
    ):
        connection.execute(
            text("UPDATE render_jobs SET status = 'DELIVERED' WHERE job_id = :job"),
            {"job": job_id},
        )


def test_canonical_job_idempotency_is_account_scoped(connection: Connection) -> None:
    account_id, quote_id, _ = create_quote_job(connection, "canonical")
    hold_id: object = connection.execute(
        text("SELECT hold_id FROM render_jobs WHERE quote_id = :quote"), {"quote": quote_id}
    ).scalar_one()
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO render_jobs "
                "(account_id, quote_id, hold_id, idempotency_key) "
                "VALUES (:account, :quote, :hold, 'render-canonical')"
            ),
            {"account": account_id, "quote": quote_id, "hold": hold_id},
        )


def test_quote_rejects_foreign_person_asset(connection: Connection) -> None:
    account_id, _, consent_id, item_id, hold_id = create_render_dependencies(connection, "owner")
    _, _, foreign_asset = create_account_asset(connection, "foreign")
    price_id: object = connection.execute(
        text("SELECT price_version_id FROM wallet_holds WHERE hold_id = :hold"), {"hold": hold_id}
    ).scalar_one()
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO render_quotes "
                "(account_id, catalog_item_id, person_asset_id, consent_id, price_version_id, "
                "token_cost, expires_at) VALUES (:account, :item, :asset, :consent, :price, 5, "
                "now() + interval '5 minutes')"
            ),
            {
                "account": account_id,
                "item": item_id,
                "asset": foreign_asset,
                "consent": consent_id,
                "price": price_id,
            },
        )


def test_result_rejects_foreign_result_asset(connection: Connection) -> None:
    account_id, _, job_id = create_quote_job(connection, "result-owner")
    source_asset: object = connection.execute(
        text(
            "SELECT q.person_asset_id FROM render_quotes q JOIN render_jobs j "
            "ON j.quote_id = q.quote_id WHERE j.job_id = :job"
        ),
        {"job": job_id},
    ).scalar_one()
    item_id: object = connection.execute(
        text(
            "SELECT q.catalog_item_id FROM render_quotes q JOIN render_jobs j "
            "ON j.quote_id = q.quote_id WHERE j.job_id = :job"
        ),
        {"job": job_id},
    ).scalar_one()
    _, _, foreign_asset = create_account_asset(connection, "foreign-result")
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO render_results "
                "(job_id, account_id, result_asset_id, source_person_asset_id, catalog_item_id, "
                "model_version, quality_state, quality_details, disclosure_version) "
                "VALUES (:job, :account, :result, :source, :item, 'model-v1', 'APPROVED', "
                "'{}'::jsonb, 'v1')"
            ),
            {
                "job": job_id,
                "account": account_id,
                "result": foreign_asset,
                "source": source_asset,
                "item": item_id,
            },
        )
