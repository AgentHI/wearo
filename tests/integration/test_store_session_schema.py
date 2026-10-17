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


def create_tenant_member(connection: Connection, slug: str) -> tuple[str, str, str]:
    account_id = str(uuid4())
    tenant_id = str(uuid4())
    principal_id = str(uuid4())
    membership_id = str(uuid4())
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:id, 'TENANT')"),
        {"id": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO business_tenants (tenant_id, account_id, slug) "
            "VALUES (:tenant, :account, :slug)"
        ),
        {"tenant": tenant_id, "account": account_id, "slug": slug},
    )
    connection.execute(
        text(
            "INSERT INTO principals "
            "(principal_id, account_id, account_kind, principal_type) "
            "VALUES (:principal, :account, 'TENANT', 'BUSINESS')"
        ),
        {"principal": principal_id, "account": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO tenant_memberships "
            "(membership_id, tenant_id, account_id, principal_id, role) "
            "VALUES (:membership, :tenant, :account, :principal, 'ASSOCIATE')"
        ),
        {
            "membership": membership_id,
            "tenant": tenant_id,
            "account": account_id,
            "principal": principal_id,
        },
    )
    return account_id, tenant_id, membership_id


def create_session(
    connection: Connection, account_id: str, tenant_id: str, membership_id: str
) -> str:
    session_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO guest_store_sessions "
            "(store_session_id, account_id, tenant_id, membership_id, state, expires_at) "
            "VALUES (:session, :account, :tenant, :membership, 'ACTIVE', now() + interval '1 hour')"
        ),
        {
            "session": session_id,
            "account": account_id,
            "tenant": tenant_id,
            "membership": membership_id,
        },
    )
    return session_id


def create_item(connection: Connection, account_id: str, tenant_id: str, suffix: str) -> str:
    category_id = str(uuid4())
    item_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO offering_categories (category_id, code, offering, enabled) "
            "VALUES (:category, :code, 'MIRROR_LITE', true)"
        ),
        {"category": category_id, "code": f"mirror-{suffix}"},
    )
    connection.execute(
        text(
            "INSERT INTO catalog_items "
            "(item_id, account_id, tenant_id, category_id, item_code, source_type, title, "
            "quality_state) VALUES (:item, :account, :tenant, :category, :code, 'GENUINE', "
            "'Test item', 'APPROVED')"
        ),
        {
            "item": item_id,
            "account": account_id,
            "tenant": tenant_id,
            "category": category_id,
            "code": f"SKU-{suffix}",
        },
    )
    return item_id


def test_session_rejects_membership_from_another_tenant(connection: Connection) -> None:
    first_account, first_tenant, _ = create_tenant_member(connection, "session-first")
    _, _, foreign_membership = create_tenant_member(connection, "session-second")
    with pytest.raises(IntegrityError), connection.begin_nested():
        create_session(connection, first_account, first_tenant, foreign_membership)


def test_finished_session_requires_immediate_revocation(connection: Connection) -> None:
    account_id, tenant_id, membership_id = create_tenant_member(connection, "session-finish")
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO guest_store_sessions "
                "(account_id, tenant_id, membership_id, state, expires_at, finished_at) "
                "VALUES (:account, :tenant, :membership, 'FINISHED', "
                "now() + interval '1 hour', now())"
            ),
            {"account": account_id, "tenant": tenant_id, "membership": membership_id},
        )


def test_enquiry_rejects_item_from_another_tenant(connection: Connection) -> None:
    account_id, tenant_id, membership_id = create_tenant_member(connection, "enquiry-first")
    foreign_account, foreign_tenant, _ = create_tenant_member(connection, "enquiry-second")
    session_id = create_session(connection, account_id, tenant_id, membership_id)
    foreign_item = create_item(connection, foreign_account, foreign_tenant, "foreign")
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO enquiries "
                "(account_id, tenant_id, store_session_id, catalog_item_id, contact_channel, "
                "contact_encrypted, contact_consent_at) VALUES (:account, :tenant, :session, "
                ":item, 'PHONE', :contact, now())"
            ),
            {
                "account": account_id,
                "tenant": tenant_id,
                "session": session_id,
                "item": foreign_item,
                "contact": b"encrypted-contact",
            },
        )


def test_aggregate_event_rejects_foreign_session(connection: Connection) -> None:
    account_id, tenant_id, _ = create_tenant_member(connection, "event-first")
    foreign_account, foreign_tenant, foreign_membership = create_tenant_member(
        connection, "event-second"
    )
    foreign_session = create_session(
        connection, foreign_account, foreign_tenant, foreign_membership
    )
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO tenant_aggregate_events "
                "(account_id, tenant_id, store_session_id, event_type, occurred_at) "
                "VALUES (:account, :tenant, :session, 'SESSION_STARTED', now())"
            ),
            {"account": account_id, "tenant": tenant_id, "session": foreign_session},
        )
