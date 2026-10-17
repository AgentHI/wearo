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


def insert_account(connection: Connection, kind: str) -> str:
    account_id = str(uuid4())
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:account_id, :kind)"),
        {"account_id": account_id, "kind": kind},
    )
    return account_id


def insert_consumer_principal(connection: Connection, account_id: str) -> str:
    principal_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO principals "
            "(principal_id, account_id, account_kind, principal_type) "
            "VALUES (:principal_id, :account_id, 'CONSUMER', 'CONSUMER')"
        ),
        {"principal_id": principal_id, "account_id": account_id},
    )
    return principal_id


def insert_asset(connection: Connection, account_id: str) -> str:
    asset_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO media_assets "
            "(asset_id, account_id, object_key, content_hash, mime_type, purpose) "
            "VALUES (:asset_id, :account_id, :object_key, :content_hash, 'image/jpeg', "
            "'PERSON_SOURCE')"
        ),
        {
            "asset_id": asset_id,
            "account_id": account_id,
            "object_key": f"private/{account_id}/{asset_id}",
            "content_hash": uuid4().hex,
        },
    )
    return asset_id


def test_consent_evidence_is_affirmative_and_immutable(connection: Connection) -> None:
    account_id = insert_account(connection, "CONSUMER")
    principal_id = insert_consumer_principal(connection, account_id)
    asset_id = insert_asset(connection, account_id)
    consent_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO consent_records "
            "(consent_id, account_id, asset_id, actor_principal_id, consent_version, purpose, "
            "permission_asserted, accepted_at) VALUES (:consent_id, :account_id, :asset_id, "
            ":principal_id, 'v1', 'TRY_ON', true, now())"
        ),
        {
            "consent_id": consent_id,
            "account_id": account_id,
            "asset_id": asset_id,
            "principal_id": principal_id,
        },
    )

    with (
        pytest.raises(DBAPIError, match="consent records are immutable"),
        connection.begin_nested(),
    ):
        connection.execute(
            text("UPDATE consent_records SET purpose = 'RESULT_SAVE' WHERE consent_id = :id"),
            {"id": consent_id},
        )


def test_report_cannot_cross_account_boundary(connection: Connection) -> None:
    owner_account = insert_account(connection, "CONSUMER")
    foreign_account = insert_account(connection, "CONSUMER")
    insert_consumer_principal(connection, owner_account)
    foreign_principal = insert_consumer_principal(connection, foreign_account)
    asset_id = insert_asset(connection, owner_account)

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO media_reports "
                "(account_id, asset_id, reported_by_principal_id, reason) "
                "VALUES (:account_id, :asset_id, :principal_id, 'PRIVACY')"
            ),
            {
                "account_id": foreign_account,
                "asset_id": asset_id,
                "principal_id": foreign_principal,
            },
        )


def test_deleted_asset_requires_deletion_timestamp(connection: Connection) -> None:
    account_id = insert_account(connection, "CONSUMER")
    insert_consumer_principal(connection, account_id)
    asset_id = insert_asset(connection, account_id)

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text("UPDATE media_assets SET deletion_state = 'DELETED' WHERE asset_id = :asset_id"),
            {"asset_id": asset_id},
        )
