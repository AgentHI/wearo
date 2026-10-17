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
    with engine.connect() as db:
        transaction = db.begin()
        yield db
        transaction.rollback()
    engine.dispose()


def seed_profile_dependencies(connection: Connection) -> tuple[str, str, str, str]:
    account_id, principal_id, asset_id, consent_id = map(lambda _: str(uuid4()), range(4))
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:a, 'CONSUMER')"), {"a": account_id}
    )
    connection.execute(
        text(
            "INSERT INTO principals "
            "(principal_id, account_id, account_kind, principal_type) "
            "VALUES (:p, :a, 'CONSUMER', 'CONSUMER')"
        ),
        {"p": principal_id, "a": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO media_assets "
            "(asset_id, account_id, object_key, content_hash, mime_type, purpose) "
            "VALUES (:m, :a, :k, 'hash', 'image/jpeg', 'PERSON_SOURCE')"
        ),
        {"m": asset_id, "a": account_id, "k": f"private/{uuid4().hex}"},
    )
    connection.execute(
        text(
            "INSERT INTO consent_records "
            "(consent_id, account_id, asset_id, actor_principal_id, consent_version, "
            "purpose, permission_asserted, accepted_at) "
            "VALUES (:c, :a, :m, :p, 'beta-v1', 'TRY_ON', true, now())"
        ),
        {"c": consent_id, "a": account_id, "m": asset_id, "p": principal_id},
    )
    return account_id, principal_id, asset_id, consent_id


def test_only_one_active_profile_per_account(connection: Connection) -> None:
    account_id, principal_id, asset_id, consent_id = seed_profile_dependencies(connection)
    values = {"a": account_id, "p": principal_id, "m": asset_id, "c": consent_id}
    statement = text(
        "INSERT INTO person_profiles "
        "(account_id, principal_id, person_asset_id, consent_id) "
        "VALUES (:a, :p, :m, :c)"
    )
    connection.execute(statement, values)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(statement, values)


def test_profile_rejects_impossible_guidance_values(connection: Connection) -> None:
    account_id, principal_id, asset_id, consent_id = seed_profile_dependencies(connection)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO person_profiles "
                "(account_id, principal_id, person_asset_id, consent_id, height_cm) "
                "VALUES (:a, :p, :m, :c, 20)"
            ),
            {"a": account_id, "p": principal_id, "m": asset_id, "c": consent_id},
        )


def test_daily_success_limit_is_database_enforced(connection: Connection) -> None:
    account_id, _, _, _ = seed_profile_dependencies(connection)
    connection.execute(
        text(
            "INSERT INTO generation_daily_usage "
            "(account_id, usage_date_ist, successful_generations) "
            "VALUES (:a, DATE '2026-10-17', 3)"
        ),
        {"a": account_id},
    )
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "UPDATE generation_daily_usage SET successful_generations = 4 WHERE account_id = :a"
            ),
            {"a": account_id},
        )
