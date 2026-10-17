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


def insert_account(connection: Connection, kind: str) -> str:
    account_id = str(uuid4())
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:account_id, :kind)"),
        {"account_id": account_id, "kind": kind},
    )
    return account_id


def insert_business_principal(connection: Connection, account_id: str) -> str:
    principal_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO principals "
            "(principal_id, account_id, account_kind, principal_type) "
            "VALUES (:principal_id, :account_id, 'TENANT', 'BUSINESS')"
        ),
        {"principal_id": principal_id, "account_id": account_id},
    )
    return principal_id


def insert_tenant(connection: Connection, account_id: str, slug: str) -> str:
    tenant_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO business_tenants (tenant_id, account_id, slug) "
            "VALUES (:tenant_id, :account_id, :slug)"
        ),
        {"tenant_id": tenant_id, "account_id": account_id, "slug": slug},
    )
    return tenant_id


def test_membership_rejects_mismatched_tenant_account(connection: Connection) -> None:
    first_account = insert_account(connection, "TENANT")
    second_account = insert_account(connection, "TENANT")
    principal_id = insert_business_principal(connection, first_account)
    second_tenant = insert_tenant(connection, second_account, "second-tenant")

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO tenant_memberships "
                "(tenant_id, account_id, principal_id, role) "
                "VALUES (:tenant_id, :account_id, :principal_id, 'ASSOCIATE')"
            ),
            {
                "tenant_id": second_tenant,
                "account_id": first_account,
                "principal_id": principal_id,
            },
        )


def test_consumer_account_has_one_consumer_principal(connection: Connection) -> None:
    account_id = insert_account(connection, "CONSUMER")
    statement = text(
        "INSERT INTO principals (account_id, account_kind, principal_type) "
        "VALUES (:account_id, 'CONSUMER', 'CONSUMER')"
    )
    connection.execute(statement, {"account_id": account_id})

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(statement, {"account_id": account_id})


def test_business_principal_cannot_use_consumer_account(connection: Connection) -> None:
    account_id = insert_account(connection, "CONSUMER")

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO principals (account_id, account_kind, principal_type) "
                "VALUES (:account_id, 'CONSUMER', 'BUSINESS')"
            ),
            {"account_id": account_id},
        )


def test_active_membership_is_unique_but_revoked_history_is_retained(
    connection: Connection,
) -> None:
    account_id = insert_account(connection, "TENANT")
    principal_id = insert_business_principal(connection, account_id)
    tenant_id = insert_tenant(connection, account_id, "membership-history")
    parameters = {
        "tenant_id": tenant_id,
        "account_id": account_id,
        "principal_id": principal_id,
    }
    connection.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, account_id, principal_id, role) "
            "VALUES (:tenant_id, :account_id, :principal_id, 'OWNER')"
        ),
        parameters,
    )

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, account_id, principal_id, role) "
                "VALUES (:tenant_id, :account_id, :principal_id, 'ASSOCIATE')"
            ),
            parameters,
        )

    connection.execute(
        text(
            "UPDATE tenant_memberships SET revoked_at = now(), updated_at = now() "
            "WHERE tenant_id = :tenant_id AND principal_id = :principal_id"
        ),
        parameters,
    )
    connection.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, account_id, principal_id, role) "
            "VALUES (:tenant_id, :account_id, :principal_id, 'ASSOCIATE')"
        ),
        parameters,
    )
