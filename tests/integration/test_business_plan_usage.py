from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Connection, create_engine, text

from apps.api.wearo_api.database import normalize_database_url
from apps.api.wearo_api.plan_usage import PostgresPlanUsage

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


class BoundConnectionEngine:
    """Keep PostgresPlanUsage on the transaction containing the temporary test tables."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def connect(self) -> Any:
        return nullcontext(self.connection)


def test_business_dashboard_metrics_use_delivered_try_ons_only(connection: Connection) -> None:
    account_id, tenant_id = uuid4(), uuid4()
    connection.execute(
        text(
            """
            CREATE TEMP TABLE plan_assignments (
              account_id uuid, tenant_id uuid, plan_code text, preview_limit integer,
              effective_from timestamptz, effective_until timestamptz,
              cancelled_at timestamptz
            );
            CREATE TEMP TABLE ledger_entries (
              account_id uuid, tenant_id uuid, entry_type text, amount bigint,
              created_at timestamptz
            );
            CREATE TEMP TABLE price_versions (
              action_code text, token_cost bigint, effective_from timestamptz,
              effective_until timestamptz
            );
            CREATE TEMP TABLE business_sponsored_tryons (
              session_id uuid, business_account_id uuid, tenant_id uuid,
              request_key text, usage_id uuid, render_job_id uuid
            );
            CREATE TEMP TABLE business_sponsored_sessions (
              session_id uuid, business_account_id uuid, tenant_id uuid,
              consumer_account_id uuid, participant_id uuid
            );
            CREATE TEMP TABLE billable_usage_records (
              usage_id uuid, account_id uuid, tenant_id uuid, action_code text, token_cost bigint
            );
            CREATE TEMP TABLE render_jobs (
              job_id uuid, account_id uuid, tenant_id uuid, idempotency_key text,
              status text, created_at timestamptz
            );
            CREATE TEMP TABLE business_participants (
              business_account_id uuid, tenant_id uuid, first_seen_at timestamptz
            );
            CREATE TEMP TABLE render_results (
              job_id uuid, provider_usage jsonb
            )
            """
        )
    )
    scope = {"account": account_id, "tenant": tenant_id}
    connection.execute(
        text(
            "INSERT INTO plan_assignments VALUES "
            "(:account, :tenant, 'LAUNCH', NULL, '2026-01-01Z', NULL, NULL)"
        ),
        scope,
    )
    connection.execute(
        text("INSERT INTO price_versions VALUES ('TRY_ON', 20, '2026-01-01Z', NULL)")
    )
    connection.execute(
        text(
            """
            INSERT INTO ledger_entries VALUES
              (:account, :tenant, 'CREDIT', 1000, '2026-01-01Z'),
              (:account, :tenant, 'DEBIT', -20, '2026-10-24T06:00:00Z'),
              (:account, :tenant, 'DEBIT', -20, '2026-10-24T07:00:00Z'),
              (:account, :tenant, 'DEBIT', -20, '2026-10-25T08:00:00Z'),
              (:account, :tenant, 'DEBIT', -20, '2026-10-25T09:00:00Z'),
              (:account, :tenant, 'RECREDIT', 20, '2026-10-25T09:05:00Z'),
              (:account, :tenant, 'DEBIT', -15, '2026-10-25T10:00:00Z')
            """
        ),
        scope,
    )

    participant_ids = (uuid4(), uuid4())
    for index, (action, status, cost) in enumerate(
        (("TRY_ON", "DELIVERED", 20),) * 3
        + (("TRY_ON", "FAILED", 20), ("IMAGE_VARIANT", "DELIVERED", 15))
    ):
        usage_id, job_id, session_id, consumer_account_id = uuid4(), uuid4(), uuid4(), uuid4()
        request_key = f"sponsored:dashboard-{index}"
        values = {
            "account": account_id,
            "tenant": tenant_id,
            "session": session_id,
            "consumer": consumer_account_id,
            "participant": participant_ids[index % 2],
            "request": request_key,
            "usage": usage_id,
            "action": action,
            "cost": cost,
            "job": job_id,
            "key": request_key.removeprefix("sponsored:"),
            "status": status,
        }
        connection.execute(
            text(
                "INSERT INTO business_sponsored_sessions VALUES "
                "(:session, :account, :tenant, :consumer, :participant)"
            ),
            values,
        )
        connection.execute(
            text(
                "INSERT INTO business_sponsored_tryons VALUES "
                "(:session, :account, :tenant, :request, :usage, :job)"
            ),
            values,
        )
        connection.execute(
            text(
                "INSERT INTO billable_usage_records VALUES "
                "(:usage, :account, :tenant, :action, :cost)"
            ),
            values,
        )
        connection.execute(
            text(
                "INSERT INTO render_jobs VALUES "
                "(:job, :consumer, NULL, :key, :status, '2026-10-25T08:00:00Z')"
            ),
            values,
        )

    snapshot = PostgresPlanUsage(BoundConnectionEngine(connection)).for_account(  # type: ignore[arg-type]
        account_id,
        tenant_id=tenant_id,
        action_code="TRY_ON",
        date_from=date(2026, 10, 24),
        date_to=date(2026, 10, 25),
    )

    assert snapshot.tokens_purchased == 1000
    assert snapshot.token_balance == 925
    assert snapshot.tokens_used == 60
    assert snapshot.previews_used == 3
    assert snapshot.previews_today == 3
    assert snapshot.unique_participants == 2
    assert snapshot.average_tokens_per_preview == 20
    assert snapshot.estimated_previews == 46
    assert snapshot.average_previews_per_day == 1.5
    assert snapshot.average_previews_per_hour == 0.0625

    connection.execute(
        text(
            "UPDATE business_sponsored_sessions "
            "SET consumer_account_id=NULL WHERE consumer_account_id IS NOT NULL"
        )
    )
    anonymized_snapshot = PostgresPlanUsage(BoundConnectionEngine(connection)).for_account(  # type: ignore[arg-type]
        account_id,
        tenant_id=tenant_id,
        action_code="TRY_ON",
        date_from=date(2026, 10, 24),
        date_to=date(2026, 10, 25),
    )
    assert anonymized_snapshot.previews_used == 3
    assert anonymized_snapshot.unique_participants == 2
    assert anonymized_snapshot.tokens_used == 60
