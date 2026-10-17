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


def create_tenant(connection: Connection, slug: str) -> tuple[str, str]:
    account_id = str(uuid4())
    tenant_id = str(uuid4())
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
    return account_id, tenant_id


def test_audit_events_are_immutable(connection: Connection) -> None:
    event_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO audit_events "
            "(audit_event_id, actor_type, action, target_type, occurred_at) "
            "VALUES (:id, 'SYSTEM', 'test.created', 'test_target', now())"
        ),
        {"id": event_id},
    )
    with pytest.raises(DBAPIError, match="audit events are immutable"), connection.begin_nested():
        connection.execute(
            text("UPDATE audit_events SET action = 'test.changed' WHERE audit_event_id = :id"),
            {"id": event_id},
        )


def test_case_rejects_mismatched_tenant_account(connection: Connection) -> None:
    first_account, _ = create_tenant(connection, "case-first")
    _, second_tenant = create_tenant(connection, "case-second")
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO operation_cases "
                "(account_id, tenant_id, case_type, opened_by_type, reason) "
                "VALUES (:account, :tenant, 'SUPPORT', 'PRINCIPAL', 'Need help')"
            ),
            {"account": first_account, "tenant": second_tenant},
        )


def test_resolved_case_requires_disposition_and_timestamp(connection: Connection) -> None:
    account_id, tenant_id = create_tenant(connection, "case-resolution")
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO operation_cases "
                "(account_id, tenant_id, case_type, state, opened_by_type, reason) "
                "VALUES (:account, :tenant, 'PAYMENT', 'RESOLVED', 'PRINCIPAL', 'Mismatch')"
            ),
            {"account": account_id, "tenant": tenant_id},
        )


def test_case_history_is_append_only(connection: Connection) -> None:
    account_id, tenant_id = create_tenant(connection, "case-history")
    case_id = str(uuid4())
    event_id = str(uuid4())
    connection.execute(
        text(
            "INSERT INTO operation_cases "
            "(case_id, account_id, tenant_id, case_type, opened_by_type, reason) "
            "VALUES (:case, :account, :tenant, 'DATA_REQUEST', 'PRINCIPAL', 'Export request')"
        ),
        {"case": case_id, "account": account_id, "tenant": tenant_id},
    )
    connection.execute(
        text(
            "INSERT INTO operation_case_events "
            "(case_event_id, case_id, account_id, tenant_id, actor_type, action, reason, "
            "to_state) VALUES (:event, :case, :account, :tenant, 'PRINCIPAL', 'OPENED', "
            "'Submitted by owner', 'SUBMITTED')"
        ),
        {"event": event_id, "case": case_id, "account": account_id, "tenant": tenant_id},
    )
    with pytest.raises(DBAPIError, match="case events are immutable"), connection.begin_nested():
        connection.execute(
            text("DELETE FROM operation_case_events WHERE case_event_id = :event"),
            {"event": event_id},
        )
