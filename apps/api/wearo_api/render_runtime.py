from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping

from .render_preflight import ModelRoute
from .tryon_authorization import (
    BusinessTryOnStatus,
    SubscriptionState,
    authorize_business_try_on,
)


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
    company_name: str | None = None
    product_kind: str | None = None
    route_candidates: tuple[ModelRoute, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def ordered_routes(self) -> tuple[ModelRoute, ...]:
        if self.route_candidates:
            return self.route_candidates
        return (ModelRoute(self.provider, self.model, self.region, "APPAREL", True),)

    @property
    def cancel_after(self) -> datetime | None:
        return _cancellation_after(self.status, self.created_at, self.updated_at)

    def can_cancel(self, *, now: datetime | None = None) -> bool:
        available_at = self.cancel_after
        return available_at is not None and (now or datetime.now(UTC)) >= available_at


@dataclass(frozen=True)
class RenderGalleryItem:
    result_id: UUID
    render_id: UUID
    result_asset_id: UUID
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class RenderGalleryPage:
    items: tuple[RenderGalleryItem, ...]
    saved_look_count: int
    page: int
    page_size: int
    has_next: bool


@dataclass(frozen=True)
class RenderQueueItem:
    render_id: UUID
    status: str
    attempts: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    cancel_after: datetime | None
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


@dataclass(frozen=True)
class PaidTryOnAllowance:
    token_balance: int
    token_cost: int | None
    remaining: int


PROCESSING_CANCELLATION_DELAY = timedelta(seconds=30)


def _cancellation_after(
    status: str,
    created_at: datetime | None,
    updated_at: datetime | None,
) -> datetime | None:
    if status == "PENDING":
        return created_at
    if status == "PROCESSING" and updated_at is not None:
        return updated_at + PROCESSING_CANCELLATION_DELAY
    return None


def _job_from_row(row: RowMapping) -> DurableRenderJob:
    raw_routes = row.get("route_candidates") or []
    if isinstance(raw_routes, str):
        raw_routes = json.loads(raw_routes)
    routes = tuple(
        ModelRoute(
            provider=str(route["provider"]),
            model=str(route["model"]),
            region=str(route["region"]),
            capability=str(route.get("capability") or "APPAREL"),
            enabled=bool(route.get("enabled", True)),
            priority=int(route.get("priority") or 1),
            release_id=UUID(str(route["release_id"])) if route.get("release_id") else None,
        )
        for route in raw_routes
        if isinstance(route, dict)
    )
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
        company_name=row["company_name"],
        product_kind=row["product_kind"],
        route_candidates=routes,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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
        q.provider_region,
        q.product_kind,
        q.route_candidates,
        j.created_at,
        j.updated_at,
        sponsored_business.display_name AS company_name
    FROM render_jobs AS j
    JOIN render_quotes AS q
      ON q.quote_id = j.quote_id AND q.account_id = j.account_id
    LEFT JOIN render_results AS r
      ON r.job_id = j.job_id AND r.account_id = j.account_id
    LEFT JOIN LATERAL (
        SELECT profile.display_name
        FROM business_sponsored_tryons sponsored
        JOIN business_profiles profile
          ON profile.tenant_id = sponsored.tenant_id
         AND profile.account_id = sponsored.business_account_id
        WHERE sponsored.render_job_id = j.job_id
        LIMIT 1
    ) AS sponsored_business ON true
"""


class PostgresRenderRuntime:
    """Transactional job, quota, and queue persistence for the upload-first beta."""

    maximum_free_generations = 3

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

    def __init__(self, engine: Engine, *, enforce_free_allowance: bool = True) -> None:
        self.engine = engine
        self.enforce_free_allowance = enforce_free_allowance

    def paid_tryon_allowance(
        self, account_id: UUID, *, now: datetime | None = None
    ) -> PaidTryOnAllowance:
        """Return spendable retail allowance using the same bucket rules as debit."""
        current = now or datetime.now(UTC)
        with self.engine.connect() as connection:
            price = connection.execute(
                text(
                    """
                        SELECT tokens_per_tryon
                        FROM retail_tryon_prices
                        WHERE effective_from <= :now
                          AND (effective_until IS NULL OR effective_until > :now)
                        ORDER BY effective_from DESC
                        LIMIT 1
                        """
                ),
                {"now": current},
            ).scalar_one_or_none()
            balances = (
                connection.execute(
                    text(
                        """
                    SELECT COALESCE(sum(balance), 0) AS token_balance,
                           COALESCE(sum(
                             CASE WHEN CAST(:cost AS bigint) IS NULL OR balance <= 0 THEN 0
                                  ELSE balance / CAST(:cost AS bigint) END
                           ), 0) AS remaining
                    FROM (
                        SELECT bucket.bucket_id,
                               COALESCE(sum(entry.amount), 0)::bigint AS balance
                        FROM wallet_buckets bucket
                        LEFT JOIN ledger_entries entry
                          ON entry.bucket_id = bucket.bucket_id
                         AND entry.account_id = bucket.account_id
                        WHERE bucket.account_id = :account
                          AND (bucket.expires_at IS NULL OR bucket.expires_at > :now)
                        GROUP BY bucket.bucket_id
                    ) spendable
                    """
                    ),
                    {"account": account_id, "now": current, "cost": price},
                )
                .mappings()
                .one()
            )
        return PaidTryOnAllowance(
            token_balance=max(int(balances["token_balance"]), 0),
            token_cost=int(price) if price is not None else None,
            remaining=max(int(balances["remaining"]), 0),
        )

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
            if self.enforce_free_allowance and not sponsored:
                usage = connection.execute(
                    text(
                        """
                    INSERT INTO consumer_free_tryon_grants
                        (account_id, grant_limit, active_job_id)
                    VALUES
                        (:account, :maximum, :job)
                    ON CONFLICT (account_id) DO UPDATE
                    SET active_job_id = EXCLUDED.active_job_id,
                        updated_at = :now
                    WHERE consumer_free_tryon_grants.successful_generations
                            < consumer_free_tryon_grants.grant_limit
                      AND consumer_free_tryon_grants.active_job_id IS NULL
                    RETURNING grant_id
                    """
                    ),
                    {
                        "account": account_id,
                        "job": job_id,
                        "maximum": self.maximum_free_generations,
                        "now": current,
                    },
                ).scalar_one_or_none()
            if self.enforce_free_allowance and not sponsored and usage is None:
                grant = (
                    connection.execute(
                        text(
                            """
                            SELECT successful_generations, grant_limit, active_job_id
                            FROM consumer_free_tryon_grants
                            WHERE account_id = :account
                            FOR UPDATE
                            """
                        ),
                        {"account": account_id},
                    )
                    .mappings()
                    .one()
                )
                if (
                    int(grant["successful_generations"]) < int(grant["grant_limit"])
                    and grant["active_job_id"] is not None
                ):
                    raise DurableRenderError(
                        "FREE_ALLOWANCE_UNAVAILABLE",
                        "Free try-ons are available, but another generation is active.",
                    )
                self._debit_paid_tryon(
                    connection,
                    job_id=job_id,
                    account_id=account_id,
                    principal_id=principal_id,
                    request_key=key,
                    now=current,
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

    def list_gallery_page(
        self,
        account_id: UUID,
        *,
        page: int = 1,
        page_size: int = 12,
        now: datetime | None = None,
    ) -> RenderGalleryPage:
        if page < 1 or not 1 <= page_size <= 50:
            raise ValueError("gallery page must be positive and page size between 1 and 50")
        current = now or datetime.now(UTC)
        offset = (page - 1) * page_size
        gallery_scope = """
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
        """
        with self.engine.connect() as connection:
            saved_look_count = int(
                connection.execute(
                    text("SELECT COUNT(*) " + gallery_scope),
                    {"account": account_id, "now": current},
                ).scalar_one()
            )
            rows = (
                connection.execute(
                    text(
                        """SELECT
                            result.result_id,
                            result.job_id AS render_id,
                            result.result_asset_id,
                            result.created_at,
                            asset.delete_after AS expires_at
                        """
                        + gallery_scope
                        + """
                        ORDER BY result.created_at DESC, result.result_id DESC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    {
                        "account": account_id,
                        "now": current,
                        "limit": page_size,
                        "offset": offset,
                    },
                )
                .mappings()
                .all()
            )
        items = tuple(
            RenderGalleryItem(
                result_id=row["result_id"],
                render_id=row["render_id"],
                result_asset_id=row["result_asset_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )
            for row in rows
        )
        return RenderGalleryPage(
            items=items,
            saved_look_count=saved_look_count,
            page=page,
            page_size=page_size,
            has_next=offset + len(items) < saved_look_count,
        )

    def list_gallery(
        self,
        account_id: UUID,
        *,
        limit: int = 30,
        now: datetime | None = None,
    ) -> tuple[RenderGalleryItem, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("gallery limit must be between 1 and 50")
        return self.list_gallery_page(
            account_id,
            page=1,
            page_size=limit,
            now=now,
        ).items

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
        items: list[RenderQueueItem] = []
        for row in rows:
            cancel_after = _cancellation_after(row["status"], row["created_at"], row["updated_at"])
            items.append(
                RenderQueueItem(
                    render_id=row["render_id"],
                    status=row["status"],
                    attempts=row["attempts"],
                    error_code=row["error_code"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    cancel_after=cancel_after,
                    can_cancel=cancel_after is not None and current >= cancel_after,
                )
            )
        return tuple(items)

    def cancel_queued(
        self,
        job_id: UUID,
        account_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DurableRenderJob:
        """Cancel an owned queued job, or a processing job after thirty seconds."""
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
                        SELECT job_id, account_id, status, created_at, updated_at,
                               billable_usage_id
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
            if work is None or locked["status"] not in {"PENDING", "PROCESSING"}:
                raise DurableRenderError(
                    "JOB_STATE_CONFLICT", "Only an active try-on can be cancelled."
                )
            expected_work_status = "PENDING" if locked["status"] == "PENDING" else "LEASED"
            if work["status"] != expected_work_status:
                raise DurableRenderError(
                    "JOB_STATE_CONFLICT", "The try-on state changed before it was cancelled."
                )
            cancel_after = _cancellation_after(
                locked["status"], locked["created_at"], locked["updated_at"]
            )
            if cancel_after is None:
                raise DurableRenderError(
                    "JOB_STATE_CONFLICT", "Only an active try-on can be cancelled."
                )
            if current < cancel_after:
                raise DurableRenderError(
                    "PROCESSING_CANCELLATION_TOO_EARLY",
                    "A processing try-on can be cancelled after 30 seconds.",
                )

            previous_status = locked["status"]
            error_code = (
                "USER_CANCELLED_QUEUED"
                if previous_status == "PENDING"
                else "USER_CANCELLED_PROCESSING"
            )
            connection.execute(
                text(
                    """
                    UPDATE render_jobs
                    SET status = 'CANCELLED', error_code = :error, updated_at = :now
                    WHERE job_id = :job AND account_id = :account AND status = :status
                    """
                ),
                {
                    "error": error_code,
                    "now": current,
                    "job": job_id,
                    "account": account_id,
                    "status": previous_status,
                },
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
                    WHERE work_item_id = :work AND status = :status
                    """
                ),
                {
                    "error": error_code,
                    "now": current,
                    "work": work["work_item_id"],
                    "status": expected_work_status,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE consumer_free_tryon_grants
                    SET active_job_id = NULL, updated_at = :now
                    WHERE account_id = :account AND active_job_id = :job
                    """
                ),
                {"account": account_id, "job": job_id, "now": current},
            )
            if locked["billable_usage_id"] is not None:
                self._recredit_paid_tryon(
                    connection,
                    account_id=account_id,
                    usage_id=locked["billable_usage_id"],
                    reason_code=(
                        "CANCELLED_BEFORE_PROCESSING"
                        if previous_status == "PENDING"
                        else "NON_DELIVERED"
                    ),
                    now=current,
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
                    SELECT work.work_item_id, work.job_id, work.account_id, work.attempts,
                           job.billable_usage_id
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
                        UPDATE consumer_free_tryon_grants
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
                if work["billable_usage_id"] is not None:
                    self._recredit_paid_tryon(
                        connection,
                        account_id=work["account_id"],
                        usage_id=work["billable_usage_id"],
                        reason_code="FAILED",
                        now=current,
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
        provider: str | None = None,
        model: str | None = None,
        region: str | None = None,
        now: datetime | None = None,
    ) -> DurableRenderJob:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            self._lock_work_for_job(connection, job_id)
            locked = self._lock_job(connection, job_id)
            if locked["status"] == "DELIVERED":
                return self._get_in_transaction(connection, job_id)
            if locked["status"] == "CANCELLED":
                # The provider call cannot always be interrupted. If it completes after
                # the user cancelled, keep the job cancelled and retire the late asset.
                connection.execute(
                    text(
                        """
                        UPDATE media_assets
                        SET deletion_state = 'REQUESTED',
                            delete_after = :now,
                            updated_at = :now
                        WHERE asset_id = :asset
                          AND account_id = :account
                          AND purpose = 'RENDER_RESULT'
                          AND deletion_state = 'RETAINED'
                        """
                    ),
                    {
                        "asset": result_asset_id,
                        "account": locked["account_id"],
                        "now": current,
                    },
                )
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
                            provider_usage,
                            product_kind,
                            product_category,
                            classification_evidence,
                            person_category,
                            age_range,
                            estimated_age
                        )
                    SELECT
                        :result,
                        j.job_id,
                        j.account_id,
                        :result_asset,
                        q.person_asset_id,
                        q.item_asset_id,
                        COALESCE(:model, q.model_version),
                        'APPROVED',
                        CAST(:quality AS jsonb),
                        'beta-v1',
                        COALESCE(:provider, q.provider),
                        COALESCE(:region, q.provider_region),
                        :provider_request,
                        CAST(:provider_usage AS jsonb),
                        q.product_kind,
                        q.product_category,
                        q.classification_evidence,
                        q.person_category,
                        q.age_range,
                        q.estimated_age
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
                    "provider": provider,
                    "model": model,
                    "region": region,
                    "job": job_id,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO model_usage_costs
                    (usage_cost_id, job_id, model_id, input_units, output_units,
                     cost_usd_micros, cost_basis)
                    SELECT gen_random_uuid(), j.job_id, model.model_id,
                      COALESCE((CAST(:provider_usage AS jsonb)->>'input_tokens')::bigint, 0),
                      COALESCE((CAST(:provider_usage AS jsonb)->>'output_tokens')::bigint, 0),
                      CASE
                        WHEN (CAST(:provider_usage AS jsonb)->>'cost_usd_micros') IS NOT NULL
                          THEN (CAST(:provider_usage AS jsonb)->>'cost_usd_micros')::bigint
                        WHEN model.billing_method='TOKEN' AND :provider_usage IS NOT NULL THEN
                          COALESCE((CAST(:provider_usage AS jsonb)->>'input_tokens')::bigint, 0)
                            * model.input_unit_price_usd_micros
                          + COALESCE((CAST(:provider_usage AS jsonb)->>'output_tokens')::bigint, 0)
                            * model.output_unit_price_usd_micros
                        WHEN model.billing_method IN ('REQUEST','IMAGE','CREDIT')
                          THEN model.request_price_usd_micros
                        ELSE model.fallback_cost_usd_micros
                      END,
                      CASE
                        WHEN (CAST(:provider_usage AS jsonb)->>'cost_usd_micros') IS NOT NULL
                          THEN 'ACTUAL'
                        WHEN :provider_usage IS NOT NULL THEN 'CALCULATED'
                        ELSE 'ESTIMATED'
                      END
                    FROM render_jobs j JOIN render_quotes q ON q.quote_id=j.quote_id
                    JOIN ai_providers provider ON provider.code=COALESCE(:provider, q.provider)
                    JOIN ai_models model ON model.provider_id=provider.provider_id
                      AND model.api_model_id=COALESCE(:model, q.model_version)
                      AND model.region=COALESCE(:region, q.provider_region)
                    WHERE j.job_id=:job
                    ON CONFLICT (job_id) DO NOTHING"""
                ),
                {
                    "job": job_id,
                    "provider_usage": json.dumps(provider_usage) if provider_usage else None,
                    "provider": provider,
                    "model": model,
                    "region": region,
                },
            )
            self._finish_job(connection, job_id, "DELIVERED", None, current)
            connection.execute(
                text(
                    """
                    UPDATE accounts AS account
                    SET product_category = quote.product_category,
                        updated_at = :now
                    FROM render_jobs AS job
                    JOIN render_quotes AS quote ON quote.quote_id = job.quote_id
                    WHERE job.job_id = :job
                      AND account.account_id = job.account_id
                      AND account.kind = 'CONSUMER'
                      AND quote.product_kind IN ('APPAREL', 'JEWELLERY')
                      AND CASE quote.product_category
                            WHEN 'ultra_luxury' THEN 4
                            WHEN 'luxury' THEN 3
                            WHEN 'premium' THEN 2
                            WHEN 'basic' THEN 1
                            ELSE 0
                          END
                          > CASE account.product_category
                              WHEN 'ultra_luxury' THEN 4
                              WHEN 'luxury' THEN 3
                              WHEN 'premium' THEN 2
                              WHEN 'basic' THEN 1
                              ELSE 0
                            END
                    """
                ),
                {"job": job_id, "now": current},
            )
            # A login may upload photos of several family members. Keep person attributes
            # on a source-photo-backed person record instead of conflating them on accounts.
            # Identical uploads already reuse one media asset, so this upsert is idempotent.
            connection.execute(
                text(
                    """
                    WITH context AS (
                        SELECT job.job_id,
                               job.account_id,
                               quote.person_asset_id,
                               quote.person_category,
                               quote.age_range,
                               quote.estimated_age,
                               consent.marketing_approved,
                               consent.marketing_tenant_id,
                               sponsored_session.tenant_id,
                               sponsored_session.business_account_id,
                               sponsored_session.store_id
                        FROM render_jobs AS job
                        JOIN render_quotes AS quote ON quote.quote_id = job.quote_id
                        JOIN consent_records AS consent
                          ON consent.consent_id = quote.consent_id
                         AND consent.account_id = quote.account_id
                        LEFT JOIN business_sponsored_tryons AS sponsored
                          ON sponsored.render_job_id = job.job_id
                        LEFT JOIN business_sponsored_sessions AS sponsored_session
                          ON sponsored_session.session_id = sponsored.session_id
                        WHERE job.job_id = :job
                          AND quote.product_kind IN ('APPAREL', 'JEWELLERY')
                    ), recorded_person AS (
                        INSERT INTO account_persons AS existing
                            (account_id, source_person_asset_id, person_category, gender,
                             age_range, estimated_age, marketing_eligible,
                             first_seen_at, last_seen_at, created_at, updated_at)
                        SELECT account_id,
                               person_asset_id,
                               person_category,
                               CASE WHEN person_category IN ('girl', 'woman')
                                    THEN 'female' ELSE 'unknown' END,
                               age_range,
                               estimated_age,
                               marketing_approved,
                               :now,
                               :now,
                               :now,
                               :now
                        FROM context
                        ON CONFLICT (account_id, source_person_asset_id) DO UPDATE SET
                            person_category = CASE
                              WHEN existing.person_category = 'unknown'
                              THEN EXCLUDED.person_category ELSE existing.person_category END,
                            gender = CASE
                              WHEN existing.gender = 'unknown'
                              THEN EXCLUDED.gender ELSE existing.gender END,
                            age_range = CASE
                              WHEN existing.age_range = 'unknown'
                              THEN EXCLUDED.age_range ELSE existing.age_range END,
                            estimated_age = COALESCE(
                              existing.estimated_age, EXCLUDED.estimated_age
                            ),
                            marketing_eligible = (
                              existing.marketing_eligible OR EXCLUDED.marketing_eligible
                            ),
                            last_seen_at = EXCLUDED.last_seen_at,
                            updated_at = EXCLUDED.updated_at
                        RETURNING person_id, account_id
                    )
                    INSERT INTO person_tryon_observations
                        (person_id, account_id, render_job_id, tenant_id,
                         business_account_id, store_id, marketing_eligible,
                         observed_at, created_at, updated_at)
                    SELECT person.person_id,
                           context.account_id,
                           context.job_id,
                           context.tenant_id,
                           context.business_account_id,
                           context.store_id,
                           COALESCE(
                             context.marketing_approved
                             AND context.marketing_tenant_id = context.tenant_id,
                             false
                           ),
                           :now,
                           :now,
                           :now
                    FROM recorded_person AS person
                    JOIN context ON context.account_id = person.account_id
                    ON CONFLICT (render_job_id) DO NOTHING
                    """
                ),
                {"job": job_id, "now": current},
            )
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
            if (
                self.enforce_free_allowance
                and not sponsored
                and locked["billable_usage_id"] is None
            ):
                usage_updated = connection.execute(
                    text(
                        """
                    UPDATE consumer_free_tryon_grants
                    SET successful_generations = successful_generations + 1,
                        active_job_id = NULL,
                        updated_at = :now
                    WHERE account_id = :account
                      AND active_job_id = :job
                      AND successful_generations < grant_limit
                    RETURNING grant_id
                    """
                    ),
                    {
                        "account": locked["account_id"],
                        "job": job_id,
                        "now": current,
                    },
                ).scalar_one_or_none()
            if (
                self.enforce_free_allowance
                and not sponsored
                and locked["billable_usage_id"] is None
                and usage_updated is None
            ):
                raise DurableRenderError(
                    "QUOTA_STATE_CONFLICT", "Free try-on allowance cannot settle."
                )
            if (
                not self.enforce_free_allowance
                or sponsored
                or locked["billable_usage_id"] is not None
            ):
                connection.execute(
                    text(
                        """
                        UPDATE consumer_free_tryon_grants
                        SET active_job_id = NULL, updated_at = :now
                        WHERE account_id = :account AND active_job_id = :job
                        """
                    ),
                    {"account": locked["account_id"], "job": job_id, "now": current},
                )
            connection.execute(
                text(
                    """INSERT INTO drive_sync_jobs
                       (connection_id, account_id, render_job_id, result_asset_id)
                       SELECT connection_id, account_id, :job, :asset
                       FROM user_drive_connections
                       WHERE account_id=:account AND status='CONNECTED' AND auto_sync_enabled
                       ON CONFLICT (render_job_id) DO NOTHING"""
                ),
                {
                    "account": locked["account_id"],
                    "job": job_id,
                    "asset": result_asset_id,
                },
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
            self._lock_work_for_job(connection, job_id)
            locked = self._lock_job(connection, job_id)
            if locked["status"] in {"FAILED", "CANCELLED"}:
                return self._get_in_transaction(connection, job_id)
            if locked["status"] != "PROCESSING":
                raise DurableRenderError("JOB_STATE_CONFLICT", "Render job is not processing.")
            self._finish_job(connection, job_id, "FAILED", safe_code, current)
            connection.execute(
                text(
                    """
                    UPDATE consumer_free_tryon_grants
                    SET active_job_id = NULL, updated_at = :now
                    WHERE account_id = :account AND active_job_id = :job
                    """
                ),
                {"account": locked["account_id"], "job": job_id, "now": current},
            )
            if locked["billable_usage_id"] is not None:
                self._recredit_paid_tryon(
                    connection,
                    account_id=locked["account_id"],
                    usage_id=locked["billable_usage_id"],
                    reason_code="FAILED",
                    now=current,
                )
            return self._get_in_transaction(connection, job_id)

    @staticmethod
    def _lock_job(connection: Connection, job_id: UUID) -> RowMapping:
        row = (
            connection.execute(
                text(
                    "SELECT job_id, account_id, status, billable_usage_id FROM render_jobs "
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
    def _lock_work_for_job(connection: Connection, job_id: UUID) -> RowMapping:
        row = (
            connection.execute(
                text(
                    "SELECT work_item_id, status FROM render_work_items "
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
    def _debit_paid_tryon(
        connection: Connection,
        *,
        job_id: UUID,
        account_id: UUID,
        principal_id: UUID,
        request_key: str,
        now: datetime,
    ) -> UUID:
        price = (
            connection.execute(
                text(
                    """
                    SELECT retail_price_id, tokens_per_tryon
                    FROM retail_tryon_prices
                    WHERE effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY effective_from DESC
                    LIMIT 1
                    """
                ),
                {"now": now},
            )
            .mappings()
            .one_or_none()
        )
        if price is None:
            raise DurableRenderError(
                "PRICE_UNAVAILABLE", "Purchased try-on pricing is unavailable."
            )
        # Lock candidate buckets before calculating their balances. Keeping the
        # balance check in a second statement prevents two concurrent renders
        # from both observing the same pre-lock ledger snapshot.
        candidates = (
            connection.execute(
                text(
                    """
                    SELECT bucket.bucket_id, bucket.wallet_id
                    FROM wallet_buckets bucket
                    WHERE bucket.account_id = :account
                      AND (bucket.expires_at IS NULL OR bucket.expires_at > :now)
                    ORDER BY (bucket.bucket_type = 'PROMO') DESC,
                             bucket.expires_at NULLS LAST,
                             bucket.created_at
                    FOR UPDATE
                    """
                ),
                {"account": account_id, "now": now},
            )
            .mappings()
            .all()
        )
        cost = int(price["tokens_per_tryon"])
        bucket = next(
            (
                candidate
                for candidate in candidates
                if int(
                    connection.execute(
                        text(
                            """
                            SELECT COALESCE(sum(amount), 0)
                            FROM ledger_entries
                            WHERE account_id = :account AND bucket_id = :bucket
                            """
                        ),
                        {"account": account_id, "bucket": candidate["bucket_id"]},
                    ).scalar_one()
                )
                >= cost
            ),
            None,
        )
        if bucket is None:
            raise DurableRenderError(
                "TRYONS_USED",
                "You have no free or purchased try-ons remaining. Buy more try-ons to continue.",
            )

        entry_id, usage_id = uuid4(), uuid4()
        connection.execute(
            text(
                """
                INSERT INTO ledger_entries
                    (entry_id, account_id, wallet_id, bucket_id, entry_type,
                     amount, operation_key, performed_by_principal_id)
                VALUES
                    (:entry, :account, :wallet, :bucket, 'DEBIT',
                     :amount, :operation, :principal)
                """
            ),
            {
                "entry": entry_id,
                "account": account_id,
                "wallet": bucket["wallet_id"],
                "bucket": bucket["bucket_id"],
                "amount": -cost,
                "operation": f"render:{job_id}",
                "principal": principal_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO billable_usage_records
                    (usage_id, account_id, principal_id, action_code, request_key,
                     retail_price_id, token_cost, ledger_entry_id, created_at)
                VALUES
                    (:usage, :account, :principal, 'TRY_ON', :request_key,
                     :retail_price, :cost, :entry, :now)
                """
            ),
            {
                "usage": usage_id,
                "account": account_id,
                "principal": principal_id,
                "request_key": request_key,
                "retail_price": price["retail_price_id"],
                "cost": cost,
                "entry": entry_id,
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                UPDATE render_jobs
                SET billable_usage_id = :usage, updated_at = :now
                WHERE job_id = :job AND account_id = :account
                """
            ),
            {"usage": usage_id, "now": now, "job": job_id, "account": account_id},
        )
        return usage_id

    @staticmethod
    def _recredit_paid_tryon(
        connection: Connection,
        *,
        account_id: UUID,
        usage_id: UUID,
        reason_code: str,
        now: datetime,
    ) -> None:
        existing = connection.execute(
            text(
                """
                SELECT recredit_id
                FROM usage_recredits
                WHERE usage_id = :usage AND account_id = :account
                """
            ),
            {"usage": usage_id, "account": account_id},
        ).scalar_one_or_none()
        if existing is not None:
            return
        usage = (
            connection.execute(
                text(
                    """
                    SELECT usage.tenant_id, usage.token_cost,
                           entry.wallet_id, entry.bucket_id
                    FROM billable_usage_records usage
                    JOIN ledger_entries entry
                      ON entry.entry_id = usage.ledger_entry_id
                     AND entry.account_id = usage.account_id
                    WHERE usage.usage_id = :usage AND usage.account_id = :account
                    FOR UPDATE OF usage
                    """
                ),
                {"usage": usage_id, "account": account_id},
            )
            .mappings()
            .one_or_none()
        )
        if usage is None:
            raise DurableRenderError(
                "BILLING_STATE_CONFLICT", "Paid try-on usage cannot be refunded."
            )
        entry_id, recredit_id = uuid4(), uuid4()
        connection.execute(
            text(
                """
                INSERT INTO ledger_entries
                    (entry_id, account_id, tenant_id, wallet_id, bucket_id,
                     entry_type, amount, operation_key)
                VALUES
                    (:entry, :account, :tenant, :wallet, :bucket,
                     'RECREDIT', :amount, :operation)
                """
            ),
            {
                "entry": entry_id,
                "account": account_id,
                "tenant": usage["tenant_id"],
                "wallet": usage["wallet_id"],
                "bucket": usage["bucket_id"],
                "amount": int(usage["token_cost"]),
                "operation": f"recredit:{usage_id}",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO usage_recredits
                    (recredit_id, usage_id, account_id, tenant_id, reason_code,
                     token_amount, ledger_entry_id, created_at)
                VALUES
                    (:recredit, :usage, :account, :tenant, :reason,
                     :amount, :entry, :now)
                """
            ),
            {
                "recredit": recredit_id,
                "usage": usage_id,
                "account": account_id,
                "tenant": usage["tenant_id"],
                "reason": reason_code,
                "amount": int(usage["token_cost"]),
                "entry": entry_id,
                "now": now,
            },
        )

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
