from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

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


def test_drive_connection_defaults_off_and_is_unique_per_wearo_account(
    connection: Connection,
) -> None:
    account_id = uuid4()
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
        {"account": account_id},
    )
    row = (
        connection.execute(
            text(
                """INSERT INTO user_drive_connections (account_id)
               VALUES (:account)
               RETURNING status, auto_sync_enabled, failed_sync_count"""
            ),
            {"account": account_id},
        )
        .mappings()
        .one()
    )

    assert row == {
        "status": "DISCONNECTED",
        "auto_sync_enabled": False,
        "failed_sync_count": 0,
    }
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text("INSERT INTO user_drive_connections (account_id) VALUES (:account)"),
            {"account": account_id},
        )


def test_drive_sync_claim_and_deduplication_indexes_exist(connection: Connection) -> None:
    index_names = set(
        connection.execute(
            text(
                """SELECT indexname FROM pg_indexes
                   WHERE schemaname=current_schema() AND tablename='drive_sync_jobs'"""
            )
        ).scalars()
    )

    assert "ix_drive_sync_jobs_claim" in index_names
    assert "uq_drive_sync_jobs_render" in index_names
    assert "ix_drive_sync_jobs_account_status" in index_names
