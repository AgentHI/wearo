from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from apps.api.wearo_api.database import normalize_database_url
from apps.api.wearo_api.render_runtime import DurableRenderError, PostgresRenderRuntime

pytestmark = pytest.mark.integration


@pytest.fixture
def engine() -> Iterator[Engine]:
    raw_url = os.environ.get("WEARO_DATABASE_URL")
    if raw_url is None:
        pytest.skip("WEARO_DATABASE_URL is required for PostgreSQL integration tests")
    database_engine = create_engine(normalize_database_url(raw_url))
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def _seed_quote(engine: Engine, ids: dict[str, UUID], quote_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
            ids,
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
        for asset, purpose in ((ids["person"], "PERSON_SOURCE"), (ids["item"], "PRODUCT_SOURCE")):
            connection.execute(
                text(
                    """
                    INSERT INTO media_assets
                        (asset_id, account_id, object_key, content_hash, mime_type, purpose)
                    VALUES
                        (:asset, :account, :key, :hash, 'image/png', :purpose)
                    """
                ),
                {
                    "asset": asset,
                    "account": ids["account"],
                    "key": f"private/{asset.hex}",
                    "hash": asset.hex,
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
                    (:consent, :account, :person, :principal, 'beta-v1', 'TRY_ON', true, now())
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
        _insert_quote(connection, ids, quote_id)


def _insert_quote(connection: Connection, ids: dict[str, UUID], quote_id: UUID) -> None:
    connection.execute(
        text(
            """
            INSERT INTO render_quotes
                (
                    quote_id,
                    account_id,
                    person_asset_id,
                    consent_id,
                    principal_id,
                    profile_id,
                    item_asset_id,
                    remaining_allowance,
                    provider,
                    model_version,
                    provider_region,
                    expires_at
                )
            VALUES
                (
                    :quote,
                    :account,
                    :person,
                    :consent,
                    :principal,
                    :profile,
                    :item,
                    3,
                    'GOOGLE_VERTEX',
                    'virtual-try-on-001',
                    'asia-southeast1',
                    now() + interval '10 minutes'
                )
            """
        ),
        {**ids, "quote": quote_id},
    )


def _cleanup(engine: Engine, account_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE consent_records DISABLE TRIGGER trg_consent_records_immutable")
        )
        try:
            for statement in (
                "DELETE FROM render_results WHERE account_id = :account",
                "DELETE FROM render_work_items WHERE account_id = :account",
                "DELETE FROM generation_daily_usage WHERE account_id = :account",
                "DELETE FROM render_jobs WHERE account_id = :account",
                "DELETE FROM render_quotes WHERE account_id = :account",
                "DELETE FROM person_profiles WHERE account_id = :account",
                "DELETE FROM consent_records WHERE account_id = :account",
                "DELETE FROM media_assets WHERE account_id = :account",
                "DELETE FROM principals WHERE account_id = :account",
                "DELETE FROM accounts WHERE account_id = :account",
            ):
                connection.execute(text(statement), {"account": account_id})
        finally:
            connection.execute(
                text("ALTER TABLE consent_records ENABLE TRIGGER trg_consent_records_immutable")
            )


def test_runtime_persists_exactly_once_success_and_releases_failure(engine: Engine) -> None:
    ids = {
        name: uuid4() for name in ("account", "principal", "person", "item", "consent", "profile")
    }
    quote_one, quote_two, quote_three, result_asset = uuid4(), uuid4(), uuid4(), uuid4()
    runtime = PostgresRenderRuntime(engine)
    now = datetime.now(UTC)
    _seed_quote(engine, ids, quote_one)
    try:
        created = runtime.create_job(
            quote_id=quote_one,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="same-command",
            now=now,
        )
        replay = runtime.create_job(
            quote_id=quote_one,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="same-command",
            now=now,
        )
        assert replay.job_id == created.job_id

        with engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM render_work_items WHERE job_id = :job"),
                    {"job": created.job_id},
                ).scalar_one()
                == 1
            )
            _insert_quote(connection, ids, quote_two)

        with pytest.raises(DurableRenderError, match="another generation is active"):
            runtime.create_job(
                quote_id=quote_two,
                account_id=ids["account"],
                principal_id=ids["principal"],
                idempotency_key="parallel-command",
                now=now,
            )

        leased = runtime.claim_next("integration-worker", now=now)
        assert leased is not None
        assert leased.job.job_id == created.job_id
        assert runtime.claim_next("other-worker", now=now) is None

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO media_assets
                        (
                            asset_id,
                            account_id,
                            object_key,
                            content_hash,
                            mime_type,
                            purpose,
                            retention_state,
                            delete_after
                        )
                    VALUES
                        (
                            :asset,
                            :account,
                            :key,
                            :hash,
                            'image/png',
                            'RENDER_RESULT',
                            'EXPIRING',
                            :delete_after
                        )
                    """
                ),
                {
                    "asset": result_asset,
                    "account": ids["account"],
                    "key": f"private/{result_asset.hex}",
                    "hash": result_asset.hex,
                    "delete_after": now + timedelta(days=30),
                },
            )

        delivered = runtime.complete_success(
            job_id=created.job_id,
            result_asset_id=result_asset,
            provider_request_id="provider-request-1",
            quality_details={"accepted": True},
            now=now,
        )
        replayed_delivery = runtime.complete_success(
            job_id=created.job_id,
            result_asset_id=result_asset,
            provider_request_id="provider-request-1",
            quality_details={"accepted": True},
            now=now,
        )
        assert delivered.status == "DELIVERED"
        assert replayed_delivery.result_asset_id == result_asset
        gallery = runtime.list_gallery(ids["account"], now=now)
        assert len(gallery) == 1
        assert gallery[0].render_id == created.job_id
        assert gallery[0].result_asset_id == result_asset
        assert runtime.list_gallery(uuid4(), now=now) == ()

        failed_job = runtime.create_job(
            quote_id=quote_two,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="failure-command",
            now=now,
        )
        assert runtime.claim_next("integration-worker", now=now) is not None
        failed = runtime.complete_failure(failed_job.job_id, "PROVIDER_TIMEOUT", now=now)
        assert failed.status == "FAILED"

        with engine.begin() as connection:
            _insert_quote(connection, ids, quote_three)
        recovered_job = runtime.create_job(
            quote_id=quote_three,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="lease-recovery-command",
            now=now,
        )
        assert runtime.claim_next("crashed-worker", now=now) is not None
        recovery = runtime.recover_expired(now=now + timedelta(minutes=6))
        assert recovery.requeued == 0 and recovery.failed == 1
        timed_out = runtime.get_job(recovered_job.job_id, ids["account"])
        assert timed_out is not None
        assert timed_out.status == "FAILED" and timed_out.error_code == "PROCESSING_TIMEOUT"

        with engine.connect() as connection:
            usage = connection.execute(
                text(
                    """
                    SELECT successful_generations, active_job_id
                    FROM generation_daily_usage
                    WHERE account_id = :account
                    """
                ),
                ids,
            ).one()
            assert usage.successful_generations == 1
            assert usage.active_job_id is None
    finally:
        _cleanup(engine, ids["account"])


def test_disabled_allowance_allows_multiple_queued_jobs(engine: Engine) -> None:
    ids = {
        name: uuid4() for name in ("account", "principal", "person", "item", "consent", "profile")
    }
    quote_one, quote_two = uuid4(), uuid4()
    runtime = PostgresRenderRuntime(engine, enforce_daily_allowance=False)
    now = datetime.now(UTC)
    _seed_quote(engine, ids, quote_one)
    try:
        with engine.begin() as connection:
            _insert_quote(connection, ids, quote_two)
        first = runtime.create_job(
            quote_id=quote_one,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="unlimited-one",
            now=now,
        )
        second = runtime.create_job(
            quote_id=quote_two,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="unlimited-two",
            now=now,
        )
        assert first.job_id != second.job_id
        queue = runtime.list_queue_activity(ids["account"], now=now)
        assert [item.render_id for item in queue] == [second.job_id, first.job_id]
        assert all(item.status == "PENDING" and item.attempts == 0 for item in queue)
        with engine.connect() as connection:
            usage_count: int = connection.execute(
                text("SELECT count(*) FROM generation_daily_usage WHERE account_id = :account"),
                ids,
            ).scalar_one()
        assert usage_count == 0
    finally:
        _cleanup(engine, ids["account"])


def test_queued_job_can_only_be_cancelled_by_owner_after_one_minute(engine: Engine) -> None:
    ids = {
        name: uuid4() for name in ("account", "principal", "person", "item", "consent", "profile")
    }
    quote_id = uuid4()
    runtime = PostgresRenderRuntime(engine)
    now = datetime.now(UTC)
    _seed_quote(engine, ids, quote_id)
    try:
        created = runtime.create_job(
            quote_id=quote_id,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="cancel-delayed-queue-item",
            now=now,
        )
        queued_at = runtime.list_queue_activity(ids["account"], now=now)
        queued_created_at = queued_at[0].created_at
        queued = runtime.list_queue_activity(
            ids["account"], now=queued_created_at + timedelta(seconds=59)
        )
        assert queued[0].can_cancel is False
        assert queued[0].cancel_after == queued_created_at + timedelta(minutes=1)

        with pytest.raises(DurableRenderError, match="after it has waited for one minute"):
            runtime.cancel_queued(
                created.job_id,
                ids["account"],
                now=queued_created_at + timedelta(seconds=59),
            )
        with pytest.raises(DurableRenderError, match="unavailable"):
            runtime.cancel_queued(
                created.job_id,
                uuid4(),
                now=now + timedelta(minutes=2),
            )

        eligible = runtime.list_queue_activity(
            ids["account"], now=queued_created_at + timedelta(minutes=1)
        )
        assert eligible[0].can_cancel is True
        cancelled = runtime.cancel_queued(
            created.job_id,
            ids["account"],
            now=queued_created_at + timedelta(minutes=1),
        )
        assert cancelled.status == "CANCELLED"
        assert cancelled.error_code == "USER_CANCELLED_STALE_QUEUE"

        with engine.connect() as connection:
            work_status: str = connection.execute(
                text("SELECT status FROM render_work_items WHERE job_id = :job"),
                {"job": created.job_id},
            ).scalar_one()
            active_job_id: UUID | None = connection.execute(
                text(
                    "SELECT active_job_id FROM generation_daily_usage WHERE account_id = :account"
                ),
                ids,
            ).scalar_one()
        assert work_status == "DONE"
        assert active_job_id is None
    finally:
        _cleanup(engine, ids["account"])
