from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, create_engine, text

from apps.api.wearo_api.database import normalize_database_url

pytestmark = pytest.mark.integration


@pytest.fixture
def connection() -> Iterator[Connection]:
    raw_url = os.environ.get("WEARO_DATABASE_URL")
    if raw_url is None:
        pytest.skip("WEARO_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(normalize_database_url(raw_url))
    with engine.connect() as db:
        transaction = db.begin()
        yield db
        transaction.rollback()
    engine.dispose()


def test_free_beta_quote_and_job_need_no_catalog_price_or_wallet_hold(
    connection: Connection,
) -> None:
    ids = {
        name: str(uuid4())
        for name in (
            "account",
            "principal",
            "person",
            "item",
            "consent",
            "profile",
            "quote",
            "job",
        )
    }
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"), ids
    )
    connection.execute(
        text(
            """
            INSERT INTO principals
                (principal_id, account_id, account_kind, principal_type)
            VALUES
                (:principal, :account, 'CONSUMER', 'CONSUMER')
            """
        ),
        ids,
    )
    for key, purpose in (("person", "PERSON_SOURCE"), ("item", "PRODUCT_SOURCE")):
        connection.execute(
            text(
                """
                INSERT INTO media_assets
                    (asset_id, account_id, object_key, content_hash, mime_type, purpose)
                VALUES
                    (:asset, :account, :object_key, :content_hash, 'image/png', :purpose)
                """
            ),
            {
                "asset": ids[key],
                "account": ids["account"],
                "object_key": f"private/{uuid4().hex}",
                "content_hash": uuid4().hex,
                "purpose": purpose,
            },
        )
    connection.execute(
        text(
            """
            INSERT INTO consent_records
                (
                    consent_id,
                    account_id,
                    asset_id,
                    actor_principal_id,
                    consent_version,
                    purpose,
                    permission_asserted,
                    accepted_at
                )
            VALUES
                (
                    :consent,
                    :account,
                    :person,
                    :principal,
                    'beta-v1',
                    'TRY_ON',
                    true,
                    now()
                )
            """
        ),
        ids,
    )
    connection.execute(
        text(
            """
            INSERT INTO person_profiles
                (profile_id, account_id, principal_id, person_asset_id, consent_id)
            VALUES
                (:profile, :account, :principal, :person, :consent)
            """
        ),
        ids,
    )
    connection.execute(
        text(
            """
            INSERT INTO render_quotes
                (
                    quote_id,
                    account_id,
                    person_asset_id,
                    consent_id,
                    status,
                    expires_at,
                    principal_id,
                    profile_id,
                    item_asset_id,
                    remaining_allowance,
                    provider,
                    model_version,
                    provider_region
                )
            VALUES
                (
                    :quote,
                    :account,
                    :person,
                    :consent,
                    'ACTIVE',
                    now() + interval '10 minutes',
                    :principal,
                    :profile,
                    :item,
                    3,
                    'GOOGLE_VERTEX',
                    'virtual-try-on-001',
                    'asia-southeast1'
                )
            """
        ),
        ids,
    )
    connection.execute(
        text(
            """
            INSERT INTO render_jobs
                (job_id, account_id, quote_id, idempotency_key)
            VALUES
                (:job, :account, :quote, 'beta-key')
            """
        ),
        ids,
    )
    row = connection.execute(
        text("SELECT hold_id, status FROM render_jobs WHERE job_id = :job"), ids
    ).one()
    assert row.hold_id is None and row.status == "PENDING"
