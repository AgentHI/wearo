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


def _seed_quote(
    engine: Engine,
    ids: dict[str, UUID],
    quote_id: UUID,
    *,
    product_kind: str | None = None,
    product_category: str = "unknown",
    person_category: str = "unknown",
    age_range: str = "unknown",
    estimated_age: int | None = None,
    marketing_approved: bool = False,
) -> None:
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
                        marketing_approved,
                        accepted_at
                    )
                VALUES
                    (:consent, :account, :person, :principal, 'beta-v1', 'TRY_ON', true,
                     :marketing_approved, now())
                """
            ),
            {**ids, "marketing_approved": marketing_approved},
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
        _insert_quote(
            connection,
            ids,
            quote_id,
            product_kind=product_kind,
            product_category=product_category,
            person_category=person_category,
            age_range=age_range,
            estimated_age=estimated_age,
        )


def _insert_quote(
    connection: Connection,
    ids: dict[str, UUID],
    quote_id: UUID,
    *,
    product_kind: str | None = None,
    product_category: str = "unknown",
    person_category: str = "unknown",
    age_range: str = "unknown",
    estimated_age: int | None = None,
) -> None:
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
                    product_kind,
                    product_category,
                    person_category,
                    age_range,
                    estimated_age,
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
                    :product_kind,
                    :product_category,
                    :person_category,
                    :age_range,
                    :estimated_age,
                    now() + interval '10 minutes'
                )
            """
        ),
        {
            **ids,
            "quote": quote_id,
            "product_kind": product_kind,
            "product_category": product_category,
            "person_category": person_category,
            "age_range": age_range,
            "estimated_age": estimated_age,
        },
    )


def _cleanup(engine: Engine, account_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE consent_records DISABLE TRIGGER trg_consent_records_immutable")
        )
        connection.execute(
            text("ALTER TABLE usage_recredits DISABLE TRIGGER trg_usage_recredits_append_only")
        )
        connection.execute(
            text("ALTER TABLE ledger_entries DISABLE TRIGGER trg_ledger_entries_append_only")
        )
        try:
            for statement in (
                "DELETE FROM render_results WHERE account_id = :account",
                "DELETE FROM render_work_items WHERE account_id = :account",
                "DELETE FROM consumer_free_tryon_grants WHERE account_id = :account",
                "DELETE FROM render_jobs WHERE account_id = :account",
                "DELETE FROM usage_recredits WHERE account_id = :account",
                "DELETE FROM billable_usage_records WHERE account_id = :account",
                "DELETE FROM render_quotes WHERE account_id = :account",
                "DELETE FROM person_profiles WHERE account_id = :account",
                "DELETE FROM consent_records WHERE account_id = :account",
                "DELETE FROM account_persons WHERE account_id = :account",
                "DELETE FROM media_assets WHERE account_id = :account",
                "DELETE FROM ledger_entries WHERE account_id = :account",
                "DELETE FROM wallet_buckets WHERE account_id = :account",
                "DELETE FROM wallets WHERE account_id = :account",
                "DELETE FROM principals WHERE account_id = :account",
                "DELETE FROM accounts WHERE account_id = :account",
            ):
                connection.execute(text(statement), {"account": account_id})
        finally:
            connection.execute(
                text("ALTER TABLE ledger_entries ENABLE TRIGGER trg_ledger_entries_append_only")
            )
            connection.execute(
                text("ALTER TABLE usage_recredits ENABLE TRIGGER trg_usage_recredits_append_only")
            )
            connection.execute(
                text("ALTER TABLE consent_records ENABLE TRIGGER trg_consent_records_immutable")
            )


def test_exhausted_free_grant_uses_retail_tokens_and_refunds_failure(engine: Engine) -> None:
    ids = {
        name: uuid4() for name in ("account", "principal", "person", "item", "consent", "profile")
    }
    quote_id, success_quote_id, retail_price_id, result_asset_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    runtime = PostgresRenderRuntime(engine)
    now = datetime.now(UTC)
    _seed_quote(engine, ids, quote_id)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO consumer_free_tryon_grants
                        (account_id, grant_limit, successful_generations)
                    VALUES (:account, 3, 3)
                    """
                ),
                ids,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO retail_tryon_prices
                        (retail_price_id, price_minor, tokens_per_tryon, currency, reason,
                         effective_from, effective_until)
                    VALUES (:price, 300, 15, 'INR', 'integration test',
                            :starts, :ends)
                    """
                ),
                {
                    "price": retail_price_id,
                    "starts": now - timedelta(seconds=1),
                    "ends": now + timedelta(hours=1),
                },
            )
            wallet_id: UUID = connection.execute(
                text("INSERT INTO wallets (account_id) VALUES (:account) RETURNING wallet_id"),
                ids,
            ).scalar_one()
            bucket_id: UUID = connection.execute(
                text(
                    """
                    INSERT INTO wallet_buckets (account_id, wallet_id, bucket_type)
                    VALUES (:account, :wallet, 'PURCHASED')
                    RETURNING bucket_id
                    """
                ),
                {"account": ids["account"], "wallet": wallet_id},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO ledger_entries
                        (account_id, wallet_id, bucket_id, entry_type, amount, operation_key)
                    VALUES (:account, :wallet, :bucket, 'CREDIT', 200, :operation)
                    """
                ),
                {
                    "account": ids["account"],
                    "wallet": wallet_id,
                    "bucket": bucket_id,
                    "operation": f"test-credit:{ids['account']}",
                },
            )

        allowance = runtime.paid_tryon_allowance(ids["account"], now=now)
        assert allowance.token_balance == 200
        assert allowance.token_cost == 15
        assert allowance.remaining == 13

        created = runtime.create_job(
            quote_id=quote_id,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="paid-render-command",
            now=now,
        )
        replay = runtime.create_job(
            quote_id=quote_id,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="paid-render-command",
            now=now,
        )
        assert replay.job_id == created.job_id
        assert runtime.paid_tryon_allowance(ids["account"], now=now).token_balance == 185

        with engine.connect() as connection:
            billing = connection.execute(
                text(
                    """
                    SELECT job.billable_usage_id, usage.retail_price_id,
                           usage.token_cost, count(entry.entry_id) AS debit_count
                    FROM render_jobs job
                    JOIN billable_usage_records usage
                      ON usage.usage_id = job.billable_usage_id
                    JOIN ledger_entries entry
                      ON entry.entry_id = usage.ledger_entry_id
                    WHERE job.job_id = :job
                    GROUP BY job.billable_usage_id, usage.retail_price_id, usage.token_cost
                    """
                ),
                {"job": created.job_id},
            ).one()
        assert billing.retail_price_id == retail_price_id
        assert billing.token_cost == 15
        assert billing.debit_count == 1

        leased = runtime.claim_next("paid-integration-worker", now=now)
        assert leased is not None and leased.job.job_id == created.job_id
        with pytest.raises(DurableRenderError, match="after 30 seconds"):
            runtime.cancel_queued(
                created.job_id,
                ids["account"],
                now=now + timedelta(seconds=29),
            )
        cancelled = runtime.cancel_queued(
            created.job_id,
            ids["account"],
            now=now + timedelta(seconds=30),
        )
        replayed_cancel = runtime.cancel_queued(
            created.job_id,
            ids["account"],
            now=now + timedelta(seconds=30),
        )
        late_failure = runtime.complete_failure(
            created.job_id, "PROVIDER_TIMEOUT", now=now + timedelta(seconds=31)
        )
        assert cancelled.status == replayed_cancel.status == late_failure.status == "CANCELLED"
        assert runtime.paid_tryon_allowance(ids["account"], now=now).token_balance == 200
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM usage_recredits WHERE account_id = :account"),
                    ids,
                ).scalar_one()
                == 1
            )

        with engine.begin() as connection:
            _insert_quote(connection, ids, success_quote_id)
            connection.execute(
                text(
                    """
                    INSERT INTO media_assets
                        (asset_id, account_id, object_key, content_hash, mime_type, purpose,
                         retention_state, delete_after)
                    VALUES
                        (:asset, :account, :key, :hash, 'image/png', 'RENDER_RESULT',
                         'EXPIRING', :delete_after)
                    """
                ),
                {
                    "asset": result_asset_id,
                    "account": ids["account"],
                    "key": f"private/{result_asset_id.hex}",
                    "hash": result_asset_id.hex,
                    "delete_after": now + timedelta(days=30),
                },
            )
        successful_job = runtime.create_job(
            quote_id=success_quote_id,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="paid-success-command",
            now=now,
        )
        leased = runtime.claim_next("paid-success-worker", now=now)
        assert leased is not None and leased.job.job_id == successful_job.job_id
        delivered = runtime.complete_success(
            job_id=successful_job.job_id,
            result_asset_id=result_asset_id,
            provider_request_id="paid-provider-request",
            quality_details={"accepted": True},
            now=now,
        )
        assert delivered.status == "DELIVERED"
        assert runtime.paid_tryon_allowance(ids["account"], now=now).token_balance == 185
        with engine.connect() as connection:
            grant = connection.execute(
                text(
                    """
                    SELECT successful_generations, active_job_id
                    FROM consumer_free_tryon_grants
                    WHERE account_id = :account
                    """
                ),
                ids,
            ).one()
        assert grant.successful_generations == 3
        assert grant.active_job_id is None
    finally:
        _cleanup(engine, ids["account"])
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM retail_tryon_prices WHERE retail_price_id = :price"),
                {"price": retail_price_id},
            )


def test_runtime_persists_exactly_once_success_and_releases_failure(engine: Engine) -> None:
    ids = {
        name: uuid4() for name in ("account", "principal", "person", "item", "consent", "profile")
    }
    quote_one, quote_two, quote_three, downgrade_quote = uuid4(), uuid4(), uuid4(), uuid4()
    result_asset, downgrade_result_asset = uuid4(), uuid4()
    runtime = PostgresRenderRuntime(engine)
    now = datetime.now(UTC)
    _seed_quote(
        engine,
        ids,
        quote_one,
        product_kind="JEWELLERY",
        product_category="ultra_luxury",
        person_category="woman",
        age_range="30_39",
        estimated_age=34,
        marketing_approved=True,
    )
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
        gallery_page = runtime.list_gallery_page(ids["account"], page=1, page_size=1, now=now)
        assert gallery_page.items == gallery
        assert gallery_page.saved_look_count == 1
        assert gallery_page.page == 1
        assert gallery_page.page_size == 1
        assert gallery_page.has_next is False
        assert runtime.list_gallery(uuid4(), now=now) == ()
        assert runtime.delete_saved_look(created.job_id, uuid4(), now=now) is False
        assert runtime.delete_saved_look(created.job_id, ids["account"], now=now) is True
        assert runtime.list_gallery(ids["account"], now=now) == ()
        assert runtime.delete_saved_look(created.job_id, ids["account"], now=now) is False

        with engine.begin() as connection:
            _insert_quote(
                connection,
                ids,
                downgrade_quote,
                product_kind="APPAREL",
                product_category="basic",
                person_category="girl",
                age_range="20_29",
                estimated_age=24,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO media_assets
                        (asset_id, account_id, object_key, content_hash, mime_type, purpose,
                         retention_state, delete_after)
                    VALUES
                        (:asset, :account, :key, :hash, 'image/png', 'RENDER_RESULT',
                         'EXPIRING', :delete_after)
                    """
                ),
                {
                    "asset": downgrade_result_asset,
                    "account": ids["account"],
                    "key": f"private/{downgrade_result_asset.hex}",
                    "hash": downgrade_result_asset.hex,
                    "delete_after": now + timedelta(days=30),
                },
            )
        downgrade_job = runtime.create_job(
            quote_id=downgrade_quote,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="girl-after-woman-command",
            now=now,
        )
        assert runtime.claim_next("integration-worker", now=now) is not None
        runtime.complete_success(
            job_id=downgrade_job.job_id,
            result_asset_id=downgrade_result_asset,
            provider_request_id="provider-request-2",
            quality_details={"accepted": True},
            now=now,
        )

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
                    FROM consumer_free_tryon_grants
                    WHERE account_id = :account
                    """
                ),
                ids,
            ).one()
            assert usage.successful_generations == 2
            assert usage.active_job_id is None
            account_categories = connection.execute(
                text(
                    "SELECT product_category, person_category, age_range, estimated_age "
                    "FROM accounts WHERE account_id = :account"
                ),
                ids,
            ).one()
            result_categories = connection.execute(
                text(
                    "SELECT product_category, person_category, age_range, estimated_age "
                    "FROM render_results WHERE job_id = :job"
                ),
                {"job": created.job_id},
            ).one()
            assert account_categories.product_category == "ultra_luxury"
            assert account_categories.person_category == "woman"
            assert account_categories.age_range == "30_39"
            assert account_categories.estimated_age == 34
            assert result_categories.product_category == "ultra_luxury"
            assert result_categories.person_category == "woman"
            assert result_categories.age_range == "30_39"
            assert result_categories.estimated_age == 34
            downgrade_result_category = connection.execute(
                text(
                    "SELECT person_category, age_range, estimated_age "
                    "FROM render_results WHERE job_id = :job"
                ),
                {"job": downgrade_job.job_id},
            ).one()
            assert downgrade_result_category.person_category == "girl"
            assert downgrade_result_category.age_range == "20_29"
            assert downgrade_result_category.estimated_age == 24
            platform_marketing_observation = connection.execute(
                text(
                    "SELECT marketing_eligible FROM person_tryon_observations "
                    "WHERE render_job_id = :job"
                ),
                {"job": created.job_id},
            ).scalar_one()
            assert platform_marketing_observation is False
    finally:
        _cleanup(engine, ids["account"])


def test_disabled_allowance_allows_multiple_queued_jobs(engine: Engine) -> None:
    ids = {
        name: uuid4() for name in ("account", "principal", "person", "item", "consent", "profile")
    }
    quote_one, quote_two = uuid4(), uuid4()
    runtime = PostgresRenderRuntime(engine, enforce_free_allowance=False)
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
                text("SELECT count(*) FROM consumer_free_tryon_grants WHERE account_id = :account"),
                ids,
            ).scalar_one()
        assert usage_count == 0
    finally:
        _cleanup(engine, ids["account"])


def test_queued_job_can_be_cancelled_immediately_only_by_owner(engine: Engine) -> None:
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
        queued = runtime.list_queue_activity(ids["account"], now=queued_created_at)
        assert queued[0].can_cancel is True
        assert queued[0].cancel_after == queued_created_at

        with pytest.raises(DurableRenderError, match="unavailable"):
            runtime.cancel_queued(
                created.job_id,
                uuid4(),
                now=now,
            )

        cancelled = runtime.cancel_queued(
            created.job_id,
            ids["account"],
            now=queued_created_at,
        )
        assert cancelled.status == "CANCELLED"
        assert cancelled.error_code == "USER_CANCELLED_QUEUED"

        with engine.connect() as connection:
            work_status: str = connection.execute(
                text("SELECT status FROM render_work_items WHERE job_id = :job"),
                {"job": created.job_id},
            ).scalar_one()
            active_job_id: UUID | None = connection.execute(
                text(
                    "SELECT active_job_id FROM consumer_free_tryon_grants "
                    "WHERE account_id = :account"
                ),
                ids,
            ).scalar_one()
        assert work_status == "DONE"
        assert active_job_id is None
    finally:
        _cleanup(engine, ids["account"])


def test_processing_job_can_be_cancelled_after_thirty_seconds(engine: Engine) -> None:
    ids = {
        name: uuid4() for name in ("account", "principal", "person", "item", "consent", "profile")
    }
    quote_id, result_asset_id = uuid4(), uuid4()
    runtime = PostgresRenderRuntime(engine)
    now = datetime.now(UTC)
    _seed_quote(engine, ids, quote_id)
    try:
        created = runtime.create_job(
            quote_id=quote_id,
            account_id=ids["account"],
            principal_id=ids["principal"],
            idempotency_key="cancel-long-processing-job",
            now=now,
        )
        leased = runtime.claim_next("processing-cancel-worker", now=now)
        assert leased is not None and leased.job.job_id == created.job_id

        before_threshold = runtime.list_queue_activity(
            ids["account"], now=now + timedelta(seconds=29)
        )
        assert before_threshold[0].status == "PROCESSING"
        assert before_threshold[0].can_cancel is False
        assert before_threshold[0].cancel_after == now + timedelta(seconds=30)

        eligible = runtime.list_queue_activity(ids["account"], now=now + timedelta(seconds=30))
        assert eligible[0].can_cancel is True
        cancelled = runtime.cancel_queued(
            created.job_id,
            ids["account"],
            now=now + timedelta(seconds=30),
        )
        assert cancelled.status == "CANCELLED"
        assert cancelled.error_code == "USER_CANCELLED_PROCESSING"

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO media_assets
                        (asset_id, account_id, object_key, content_hash, mime_type, purpose,
                         retention_state, delete_after)
                    VALUES
                        (:asset, :account, :key, :hash, 'image/png', 'RENDER_RESULT',
                         'EXPIRING', :delete_after)
                    """
                ),
                {
                    "asset": result_asset_id,
                    "account": ids["account"],
                    "key": f"private/{result_asset_id.hex}",
                    "hash": result_asset_id.hex,
                    "delete_after": now + timedelta(days=30),
                },
            )

        late_result = runtime.complete_success(
            job_id=created.job_id,
            result_asset_id=result_asset_id,
            provider_request_id="late-provider-result",
            quality_details={"accepted": True},
            now=now + timedelta(seconds=31),
        )
        assert late_result.status == "CANCELLED"
        with engine.connect() as connection:
            state = connection.execute(
                text(
                    """
                    SELECT work.status, work.leased_by, work.lease_expires_at,
                           asset.deletion_state,
                           (SELECT count(*) FROM render_results result
                            WHERE result.job_id = :job) AS result_count
                    FROM render_work_items work
                    JOIN media_assets asset ON asset.asset_id = :asset
                    WHERE work.job_id = :job
                    """
                ),
                {"job": created.job_id, "asset": result_asset_id},
            ).one()
        assert state.status == "DONE"
        assert state.leased_by is None and state.lease_expires_at is None
        assert state.deletion_state == "REQUESTED"
        assert state.result_count == 0
    finally:
        _cleanup(engine, ids["account"])
