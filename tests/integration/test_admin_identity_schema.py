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


def insert_admin(connection: Connection) -> str:
    admin_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO admin_identities "
            "(admin_id, username, password_hash, mfa_secret_encrypted, scopes) "
            "VALUES (:id, :username, :password_hash, :secret, ARRAY['tenant:write'])"
        ),
        {
            "id": admin_id,
            "username": f"{admin_id}@wearo.test",
            "password_hash": b"scrypt-hash",
            "secret": b"encrypted-secret",
        },
    )
    return admin_id


def test_admin_username_must_be_normalized(connection: Connection) -> None:
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO admin_identities "
                "(username, password_hash, mfa_secret_encrypted, scopes) "
                "VALUES ('Admin@Wearo.Test', :hash, :secret, ARRAY['audit:read'])"
            ),
            {"hash": b"hash", "secret": b"encrypted"},
        )


def test_admin_session_realm_cannot_be_changed(connection: Connection) -> None:
    admin_id = insert_admin(connection)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO admin_sessions "
                "(admin_id, session_token_hash, csrf_token_hash, scopes, auth_realm, expires_at) "
                "VALUES (:admin, :session, :csrf, ARRAY['audit:read'], 'BUSINESS', "
                "now() + interval '10 minutes')"
            ),
            {"admin": admin_id, "session": b"session-hash", "csrf": b"csrf-hash"},
        )


def test_recovery_code_hash_is_single_use_across_admin_realm(connection: Connection) -> None:
    first_admin = insert_admin(connection)
    second_admin = insert_admin(connection)
    statement = text(
        "INSERT INTO admin_recovery_codes (admin_id, code_hash) VALUES (:admin, :hash)"
    )
    connection.execute(statement, {"admin": first_admin, "hash": b"same-code-hash"})
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(statement, {"admin": second_admin, "hash": b"same-code-hash"})
