from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping

from .tryon_authorization import (
    BusinessTryOnStatus,
    SubscriptionState,
    authorize_business_try_on,
)

IST = ZoneInfo("Asia/Kolkata")


class DurableRenderError(ValueError):
    """A safe render persistence error suitable for translation at the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DurableRenderJob:
    job_id: UUID
    quote_id: UUID
    account_id: UUID
    principal_id: UUID
    status: str
    person_asset_id: UUID
    item_asset_id: UUID
    result_asset_id: UUID | None
    error_code: str | None
    provider_request_id: str | None
    provider: str = "GOOGLE_VERTEX"
    model: str = "virtual-try-on-001"
    region: str = "asia-southeast1"


@dataclass(frozen=True)
class RenderGalleryItem:
    result_id: UUID
    render_id: UUID
    result_asset_id: UUID
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class RenderQueueItem:
    render_id: UUID
    status: str
    attempts: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    cancel_after: datetime
    can_cancel: bool


@dataclass(frozen=True)
class LeasedRenderWork:
    work_item_id: UUID
    job: DurableRenderJob
    attempts: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class RecoverySummary:
    requeued: int
    failed: int


def _usage_date(now: datetime) -> date:
    return now.astimezone(IST).date()


def _job_from_row(row: RowMapping) -> DurableRenderJob:
    return DurableRenderJob(
        job_id=row["job_id"],
        quote_id=row["quote_id"],
        account_id=row["account_id"],
        principal_id=row["principal_id"],
        status=row["status"],
        person_asset_id=row["person_asset_id"],
        item_asset_id=row["item_asset_id"],
        result_asset_id=row["result_asset_id"],
        error_code=row["error_code"],
        provider_request_id=row["provider_request_id"],
        provider=row["provider"],
        model=row["model_version"],
        region=row["provider_region"],
    )


JOB_SELECT = """
    SELECT
        j.job_id,
        j.quote_id,
        j.account_id,
        q.principal_id,
        j.status,
        q.person_asset_id,
        q.item_asset_id,
        r.result_asset_id,
        j.error_code,
        r.provider_request_id,
        q.provider,
        q.model_version,
        q.provider_region
    FROM render_jobs AS j
    JOIN render_quotes AS q
      ON q.quote_id = j.quote_id AND q.account_id = j.account_id
    LEFT JOIN render_results AS r
      ON r.job_id = j.job_id AND r.account_id = j.account_id
"""


class PostgresRenderRuntime:
    """Transactional job, quota, and queue persistence for the upload-first beta."""

    maximum_daily_generations = 3

    @staticmethod
    def _link_sponsored_render(
        connection: Connection, job_id: UUID, account_id: UUID, key: str
    ) -> bool:
        links = connection.execute(
            text(
                """
                UPDATE business_sponsored_tryons sponsored
                SET render_job_id = :job
                FROM business_sponsored_sessions session
                WHERE session.session_id = sponsored.session_id
                  AND sponsored.request_key = 'sponsored:' || :key
                  AND session.consumer_account_id = :account
                  AND sponsored.render_job_id IS NULL
                """
            ),
            {"job": job_id, "key": key, "account": account_id},
        )
        return links.rowcount > 0

    def __init__(self, engine: Engine, *, enforce_daily_allowance: bool = True) -> None:
        self.engine = engine
        self.enforce_daily_allowance = enforce_daily_allowance

    def create_job(
        self,
        *,
        quote_id: UUID,
        account_id: UUID,
        principal_id: UUID,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> DurableRenderJob:
        current = now or datetime.now(UTC)
        key = idempotency_key.strip()
        if not key or len(key) > 100:
            raise DurableRenderError("INVALID_IDEMPOTENCY_KEY", "Valid idempotency key required.")

        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    text(
                        JOB_SELECT + " WHERE j.account_id = :account AND j.idempotency_key = :key"
                    ),
                    {"account": account_id, "key": key},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                self._link_sponsored_render(connection, existing["job_id"], account_id, key)
                return _job_from_row(existing)

            sponsored_access = (
                connection.execute(
                    text(
                        """SELECT tenant.try_on_status, subscription.state AS subscription_state,
                      COALESCE((SELECT NOT paused FROM platform_tryon_controls
                        WHERE scope='PLATFORM' AND scope_key='ALL'), true) platform_operational,
                      COALESCE((SELECT NOT control.paused FROM platform_tryon_controls control
                        JOIN business_profiles profile ON profile.tenant_id=tenant.tenant_id
                          AND profile.account_id=tenant.account_id
                        WHERE control.scope='BUSINESS_TYPE'
                          AND control.scope_key=profile.operating_profile), true)
                        business_type_operational
                    FROM business_sponsored_tryons sponsored
                    JOIN business_sponsored_sessions session
                      ON session.session_id=sponsored.session_id
                    JOIN business_tenants tenant
                      ON tenant.tenant_id=sponsored.tenant_id
                     AND tenant.account_id=sponsored.business_account_id
                    JOIN business_subscriptions subscription
                      ON subscription.tenant_id=tenant.tenant_id
                     AND subscription.account_id=tenant.account_id
                    WHERE sponsored.request_key='sponsored:' || :key
                      AND session.consumer_account_id=:account"""
                    ),
                    {"key": key, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if sponsored_access is not None:
                authorize_business_try_on(
                    cast(BusinessTryOnStatus, sponsored_access["try_on_status"]),
                    cast(SubscriptionState, sponsored_access["subscription_state"]),
                    platform_operational=bool(sponsored_access["platform_operational"]),
                    business_type_operational=bool(sponsored_access["business_type_operational"]),
                )

            quote = connection.execute(
                text(
                    """
                    SELECT quote_id
                    FROM render_quotes
                    WHERE quote_id = :quote
                      AND account_id = :account
                      AND principal_id = :principal
                      AND status = 'ACTIVE'
                      AND expires_at > :now
                      AND profile_id IS NOT NULL
                      AND item_asset_id IS NOT NULL
                    FOR UPDATE
                    """
                ),
                {
                    "quote": quote_id,
                    "account": account_id,
                    "principal": principal_id,
                    "now": current,
                },
            ).scalar_one_or_none()
            if quote is None:
                raise DurableRenderError("QUOTE_UNAVAILABLE", "Quote is unavailable or expired.")

            job_id = uuid4()
            inserted = connection.execute(
                text(
                    """
                    INSERT INTO render_jobs
                        (job_id, account_id, quote_id, idempotency_key)
                    VALUES
                        (:job, :account, :quote, :key)
                    ON CONFLICT DO NOTHING
                    RETURNING job_id
                    """
                ),
                {"job": job_id, "account": account_id, "quote": quote_id, "key": key},
            ).scalar_one_or_none()
            if inserted is None:
                canonical = (
                    connection.execute(
                        text(
                            JOB_SELECT
                            + """
                          WHERE j.account_id = :account
                            AND (j.idempotency_key = :key OR j.quote_id = :quote)
                          ORDER BY (j.idempotency_key = :key) DESC
                          LIMIT 1
                        """
                        ),
                        {"account": account_id, "key": key, "quote": quote_id},
                    )
                    .mappings()
                    .one()
                )
                self._link_sponsored_render(connection, canonical["job_id"], account_id, key)
                return _job_from_row(canonical)

            sponsored = self._link_sponsored_render(connection, job_id, account_id, key)
            usage = None
            if self.enforce_daily_allowance and not sponsored:
                usage = connection.execute(
                    text(
                        """
                    INSERT INTO generation_daily_usage
                        (account_id, usage_date_ist, active_job_id)
                    VALUES
                        (:account, :usage_date, :job)
                    ON CONFLICT (account_id, usage_date_ist) DO UPDATE
                    SET active_job_id = EXCLUDED.active_job_id,
                        updated_at = :now
                    WHERE generation_daily_usage.successful_generations < :maximum
                      AND generation_daily_usage.active_job_id IS NULL
                    RETURNING usage_id
                    """
                    ),
                    {
                        "account": account_id,
                        "usage_date": _usage_date(current),
                        "job": job_id,
                        "maximum": self.maximum_daily_generations,
                        "now": current,
                    },
                ).scalar_one_or_none()
            if self.enforce_daily_allowance and not sponsored and usage is None:
                raise DurableRenderError(
                    "DAILY_ALLOWANCE_UNAVAILABLE",
                    "Daily allowance is used or another generation is active.",
                )

            connection.execute(
                text(
                    """
                    INSERT INTO render_work_items (job_id, account_id, available_at)
                    VALUES (:job, :account, :now)
                    """
                ),
                {"job": job_id, "account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    UPDATE render_quotes
                    SET status = 'USED', updated_at = :now
                    WHERE quote_id = :quote AND account_id = :account
                    """
                ),
                {"quote": quote_id, "account": account_id, "now": current},
            )
            created = (
                connection.execute(text(JOB_SELECT + " WHERE j.job_id = :job"), {"job": job_id})
                .mappings()
                .one()
            )
            return _job_from_row(created)

    def get_job(self, job_id: UUID, account_id: UUID) -> DurableRenderJob | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(JOB_SELECT + " WHERE j.job_id = :job AND j.account_id = :account"),
                    {"job": job_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
        return _job_from_row(row) if row is not None else None

    def list_gallery(
        self,
        account_id: UUID,
        *,
        limit: int = 30,
        now: datetime | None = None,
    ) -> tuple[RenderGalleryItem, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("gallery limit must be between 1 and 50")
        current = now or datetime.now(UTC)
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                            result.result_id,
                            result.job_id AS render_id,
                            result.result_asset_id,
                            result.created_at,
                            asset.delete_after AS expires_at
                        FROM render_results AS result
                        JOIN render_jobs AS job
                          ON job.job_id = result.job_id
                         AND job.account_id = result.account_id
                        JOIN media_assets AS asset
                          ON asset.asset_id = result.result_asset_id
                         AND asset.account_id = result.account_id
                        WHERE result.account_id = :account
                          AND result.quality_state = 'APPROVED'
                          AND job.status = 'DELIVERED'
                          AND asset.deletion_state = 'RETAINED'
                          AND asset.retention_state <> 'LEGAL_HOLD'
                          AND asset.delete_after > :now
                        ORDER BY result.created_at DESC, result.result_id DESC
                        LIMIT :limit
                        """
                    ),
                    {"account": account_id, "now": current, "limit": limit},
                )
                .mappings()
                .all()
            )
        return tuple(
            RenderGalleryItem(
                result_id=row["result_id"],
                render_id=row["render_id"],
                result_asset_id=row["result_asset_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )
            for row in rows
        )

    def delete_saved_look(
        self,
        render_id: UUID,
        account_id: UUID,
        *,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            deleted = connection.execute(
                text(
                    """
                    UPDATE media_assets AS asset
                    SET deletion_state = 'REQUESTED',
                        delete_after = :delete_after,
                        updated_at = :now
                    WHERE asset.account_id = :account
                      AND asset.deletion_state = 'RETAINED'
                      AND EXISTS (
                          SELECT 1
                          FROM render_results AS result
                          JOIN render_jobs AS job
                            ON job.job_id = result.job_id
                           AND job.account_id = result.account_id
                          WHERE result.job_id = :render
                            AND result.account_id = :account
                            AND result.result_asset_id = asset.asset_id
                            AND result.quality_state = 'APPROVED'
                            AND job.status = 'DELIVERED'
                      )
                    RETURNING asset.asset_id
                    """
                ),
                {
                    "render": render_id,
                    "account": account_id,
                    "now": current,
                    "delete_after": current + timedelta(hours=24),
                },
            ).scalar_one_or_none()
        return deleted is not None

    def list_queue_activity(
        self,
        account_id: UUID,
        *,
        limit: int = 30,
        now: datetime | None = None,
    ) -> tuple[RenderQueueItem, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("queue activity limit must be between 1 and 50")
        current = now or datetime.now(UTC)
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                            job.job_id AS render_id,
                            job.status,
                            COALESCE(work.attempts, 0) AS attempts,
                            job.error_code,
                            job.created_at,
                            job.updated_at
                        FROM render_jobs AS job
                        LEFT JOIN render_work_items AS work
                          ON work.job_id = job.job_id
                         AND work.account_id = job.account_id
                        WHERE job.account_id = :account
                          AND job.status IN ('PENDING', 'PROCESSING', 'FAILED', 'CANCELLED')
                          AND job.created_at > :cutoff
                        ORDER BY
                            CASE job.status
                                WHEN 'PROCESSING' THEN 0
                                WHEN 'PENDING' THEN 1
                                ELSE 2
                            END,
                            job.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {
                        "account": account_id,
                        "cutoff": current - timedelta(days=30),
                        "limit": limit,
                    },
                )
                .mappings()
                .all()
            )
        return tuple(
            RenderQueueItem(
                render_id=row["render_id"],
                status=row["status"],
                attempts=row["attempts"],
                error_code=row["error_code"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                cancel_after=row["created_at"] + timedelta(minutes=1),
                can_cancel=(
                    row["status"] == "PENDING"
                    and current >= row["created_at"] + timedelta(minutes=1)
                ),
            )
            for row in rows
        )

    def cancel_queued(
        self,
        job_id: UUID,
        account_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DurableRenderJob:
        """Cancel an owned job that has remained pending for at least one minute."""
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            # Lock in the same work-item-then-job order used by claim_next so a worker
            # and a cancellation cannot both take ownership of the queued job.
            work = (
                connection.execute(
                    text(
                        """
                        SELECT work_item_id, status
                        FROM render_work_items
                        WHERE job_id = :job
                          AND account_id = :account
                          AND status = 'PENDING'
                        FOR UPDATE
                        """
                    ),
                    {"job": job_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            locked = (
                connection.execute(
                    text(
                        """
                        SELECT job_id, account_id, status, created_at
                        FROM render_jobs
                        WHERE job_id = :job AND account_id = :account
                        FOR UPDATE
                        """
                    ),
                    {"job": job_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if locked is None:
                raise DurableRenderError("JOB_UNAVAILABLE", "Render job is unavailable.")
            if locked["status"] == "CANCELLED":
                return self._get_in_transaction(connection, job_id)
            if locked["status"] != "PENDING" or work is None:
                raise DurableRenderError(
                    "JOB_STATE_CONFLICT", "Only a queued render can be removed."
                )
            if current < locked["created_at"] + timedelta(minutes=1):
                raise DurableRenderError(
                    "QUEUE_CANCELLATION_TOO_EARLY",
                    "A queued render can be removed after it has waited for one minute.",
                )

            error_code = "USER_CANCELLED_STALE_QUEUE"
            connection.execute(
                text(
                    """
                    UPDATE render_jobs
                    SET status = 'CANCELLED', error_code = :error, updated_at = :now
                    WHERE job_id = :job AND account_id = :account AND status = 'PENDING'
                    """
                ),
                {
                    "error": error_code,
                    "now": current,
                    "job": job_id,
                    "account": account_id,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE render_work_items
                    SET status = 'DONE', last_error = :error, updated_at = :now
                    WHERE work_item_id = :work AND status = 'PENDING'
                    """
                ),
                {"error": error_code, "now": current, "work": work["work_item_id"]},
            )
            connection.execute(
                text(
                    """
                    UPDATE generation_daily_usage
                    SET active_job_id = NULL, updated_at = :now
                    WHERE account_id = :account AND active_job_id = :job
                    """
                ),
                {"account": account_id, "job": job_id, "now": current},
            )
            return self._get_in_transaction(connection, job_id)

    def claim_next(
        self,
        worker_id: str,
        *,
        now: datetime | None = None,
        lease_for: timedelta = timedelta(minutes=5),
    ) -> LeasedRenderWork | None:
        current = now or datetime.now(UTC)
        if not worker_id.strip() or lease_for <= timedelta(0):
            raise ValueError("worker identity and a positive lease are required")
        lease_expires = current + lease_for
        with self.engine.begin() as connection:
            work = (
                connection.execute(
                    text(
                        """
                    WITH candidate AS (
                        SELECT work_item_id
                        FROM render_work_items
                        WHERE status = 'PENDING' AND available_at <= :now
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE render_work_items AS work
                    SET status = 'LEASED',
                        attempts = attempts + 1,
                        leased_by = :worker,
                        lease_expires_at = :lease_expires,
                        updated_at = :now
                    FROM candidate
                    WHERE work.work_item_id = candidate.work_item_id
                    RETURNING work.work_item_id, work.job_id, work.attempts
                    """
                    ),
                    {"now": current, "worker": worker_id, "lease_expires": lease_expires},
                )
                .mappings()
                .one_or_none()
            )
            if work is None:
                return None
            transitioned = connection.execute(
                text(
                    """
                    UPDATE render_jobs
                    SET status = CASE
                            WHEN status = 'PENDING' THEN 'PROCESSING'
                            ELSE status
                        END,
                        updated_at = :now
                    WHERE job_id = :job AND status IN ('PENDING', 'PROCESSING')
                    RETURNING account_id
                    """
                ),
                {"job": work["job_id"], "now": current},
            ).scalar_one_or_none()
            if transitioned is None:
                raise DurableRenderError("JOB_STATE_CONFLICT", "Render job cannot be leased.")
            job_row = (
                connection.execute(
                    text(JOB_SELECT + " WHERE j.job_id = :job"), {"job": work["job_id"]}
                )
                .mappings()
                .one()
            )
            return LeasedRenderWork(
                work_item_id=work["work_item_id"],
                job=_job_from_row(job_row),
                attempts=work["attempts"],
                lease_expires_at=lease_expires,
            )

    def recover_expired(self, *, now: datetime | None = None) -> RecoverySummary:
        current = now or datetime.now(UTC)
        failed = 0
        with self.engine.begin() as connection:
            expired = (
                connection.execute(
                    text(
                        """
                    SELECT work.work_item_id, work.job_id, work.account_id, work.attempts
                    FROM render_work_items AS work
                    JOIN render_jobs AS job ON job.job_id = work.job_id
                    WHERE work.status = 'LEASED'
                      AND work.lease_expires_at <= :now
                      AND job.status = 'PROCESSING'
                    ORDER BY work.lease_expires_at
                    FOR UPDATE SKIP LOCKED
                    """
                    ),
                    {"now": current},
                )
                .mappings()
                .all()
            )
            for work in expired:
                connection.execute(
                    text(
                        """
                        UPDATE render_jobs
                        SET status = 'FAILED',
                            error_code = 'PROCESSING_TIMEOUT',
                            updated_at = :now
                        WHERE job_id = :job AND status = 'PROCESSING'
                        """
                    ),
                    {"job": work["job_id"], "now": current},
                )
                connection.execute(
                    text(
                        """
                        UPDATE render_work_items
                        SET status = 'DEAD',
                            leased_by = NULL,
                            lease_expires_at = NULL,
                            last_error = 'PROCESSING_TIMEOUT',
                            updated_at = :now
                        WHERE work_item_id = :work
                        """
                    ),
                    {"work": work["work_item_id"], "now": current},
                )
                connection.execute(
                    text(
                        """
                        UPDATE generation_daily_usage
                        SET active_job_id = NULL, updated_at = :now
                        WHERE account_id = :account AND active_job_id = :job
                        """
                    ),
                    {
                        "account": work["account_id"],
                        "job": work["job_id"],
                        "now": current,
                    },
                )
                failed += 1
        return RecoverySummary(0, failed)

    def complete_success(
        self,
        *,
        job_id: UUID,
        result_asset_id: UUID,
        provider_request_id: str,
        quality_details: dict[str, Any],
        provider_usage: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> DurableRenderJob:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            locked = self._lock_job(connection, job_id)
            if locked["status"] == "DELIVERED":
                return self._get_in_transaction(connection, job_id)
            if locked["status"] != "PROCESSING":
                raise DurableRenderError("JOB_STATE_CONFLICT", "Render job is not processing.")
            connection.execute(
                text(
                    """
                    INSERT INTO render_results
                        (
                            result_id,
                            job_id,
                            account_id,
                            result_asset_id,
                            source_person_asset_id,
                            source_item_asset_id,
                            model_version,
                            quality_state,
                            quality_details,
                            disclosure_version,
                            provider,
                            provider_region,
                            provider_request_id,
                            provider_usage
                        )
                    SELECT
                        :result,
                        j.job_id,
                        j.account_id,
                        :result_asset,
                        q.person_asset_id,
                        q.item_asset_id,
                        q.model_version,
                        'APPROVED',
                        CAST(:quality AS jsonb),
                        'beta-v1',
                        q.provider,
                        q.provider_region,
                        :provider_request,
                        CAST(:provider_usage AS jsonb)
                    FROM render_jobs AS j
                    JOIN render_quotes AS q ON q.quote_id = j.quote_id
                    WHERE j.job_id = :job
                    """
                ),
                {
                    "result": uuid4(),
                    "result_asset": result_asset_id,
                    "quality": json.dumps(quality_details),
                    "provider_request": provider_request_id,
                    "provider_usage": json.dumps(provider_usage) if provider_usage else None,
                    "job": job_id,
                },
            )
            self._finish_job(connection, job_id, "DELIVERED", None, current)
            sponsored = bool(
                connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM business_sponsored_tryons sponsored
                            WHERE sponsored.render_job_id = :job
                        )
                        """
                    ),
                    {"job": job_id},
                ).scalar_one()
            )
            usage_updated = None
            if self.enforce_daily_allowance and not sponsored:
                usage_updated = connection.execute(
                    text(
                        """
                    UPDATE generation_daily_usage
                    SET successful_generations = successful_generations + 1,
                        active_job_id = NULL,
                        updated_at = :now
                    WHERE account_id = :account
                      AND usage_date_ist = :usage_date
                      AND active_job_id = :job
                      AND successful_generations < :maximum
                    RETURNING usage_id
                    """
                    ),
                    {
                        "account": locked["account_id"],
                        "usage_date": _usage_date(current),
                        "job": job_id,
                        "maximum": self.maximum_daily_generations,
                        "now": current,
                    },
                ).scalar_one_or_none()
            if self.enforce_daily_allowance and not sponsored and usage_updated is None:
                raise DurableRenderError("QUOTA_STATE_CONFLICT", "Daily allowance cannot settle.")
            if not self.enforce_daily_allowance or sponsored:
                connection.execute(
                    text(
                        """
                        UPDATE generation_daily_usage
                        SET active_job_id = NULL, updated_at = :now
                        WHERE account_id = :account AND active_job_id = :job
                        """
                    ),
                    {"account": locked["account_id"], "job": job_id, "now": current},
                )
            return self._get_in_transaction(connection, job_id)

    def complete_failure(
        self, job_id: UUID, error_code: str, *, now: datetime | None = None
    ) -> DurableRenderJob:
        current = now or datetime.now(UTC)
        safe_code = error_code.strip()[:80]
        if not safe_code:
            raise ValueError("error code is required")
        with self.engine.begin() as connection:
            locked = self._lock_job(connection, job_id)
            if locked["status"] == "FAILED":
                return self._get_in_transaction(connection, job_id)
            if locked["status"] != "PROCESSING":
                raise DurableRenderError("JOB_STATE_CONFLICT", "Render job is not processing.")
            self._finish_job(connection, job_id, "FAILED", safe_code, current)
            connection.execute(
                text(
                    """
                    UPDATE generation_daily_usage
                    SET active_job_id = NULL, updated_at = :now
                    WHERE account_id = :account AND active_job_id = :job
                    """
                ),
                {"account": locked["account_id"], "job": job_id, "now": current},
            )
            return self._get_in_transaction(connection, job_id)

    @staticmethod
    def _lock_job(connection: Connection, job_id: UUID) -> RowMapping:
        row = (
            connection.execute(
                text(
                    "SELECT job_id, account_id, status FROM render_jobs "
                    "WHERE job_id = :job FOR UPDATE"
                ),
                {"job": job_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DurableRenderError("JOB_UNAVAILABLE", "Render job is unavailable.")
        return row

    @staticmethod
    def _finish_job(
        connection: Connection,
        job_id: UUID,
        status: str,
        error_code: str | None,
        now: datetime,
    ) -> None:
        connection.execute(
            text(
                """
                UPDATE render_jobs
                SET status = :status, error_code = :error, updated_at = :now
                WHERE job_id = :job AND status = 'PROCESSING'
                """
            ),
            {"status": status, "error": error_code, "now": now, "job": job_id},
        )
        connection.execute(
            text(
                """
                UPDATE render_work_items
                SET status = 'DONE',
                    leased_by = NULL,
                    lease_expires_at = NULL,
                    last_error = :error,
                    updated_at = :now
                WHERE job_id = :job AND status = 'LEASED'
                """
            ),
            {"error": error_code, "now": now, "job": job_id},
        )

    @staticmethod
    def _get_in_transaction(connection: Connection, job_id: UUID) -> DurableRenderJob:
        row = (
            connection.execute(text(JOB_SELECT + " WHERE j.job_id = :job"), {"job": job_id})
            .mappings()
            .one()
        )
        return _job_from_row(row)
