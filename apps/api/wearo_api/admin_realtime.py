from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic

from sqlalchemy import Engine, text


class AdminRealtimeError(ValueError):
    pass


class PostgresAdminRealtime:
    """Short-lived in-memory view over the durable render and attempt tables."""

    def __init__(
        self,
        engine: Engine,
        estimated_cost_minor: int = 0,
        *,
        cache_seconds: float = 2.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if estimated_cost_minor < 0 or cache_seconds < 0:
            raise AdminRealtimeError("Realtime cost and cache duration must not be negative.")
        self.engine = engine
        self.estimated_cost_minor = estimated_cost_minor
        self.cache_seconds = cache_seconds
        self.clock = clock
        self._lock = Lock()
        self._cached: dict[int, tuple[float, dict[str, object]]] = {}

    def snapshot(self, *, window_minutes: int = 60) -> dict[str, object]:
        if not 1 <= window_minutes <= 10_080:
            raise AdminRealtimeError("Realtime window must be between 1 minute and 7 days.")
        now = self.clock()
        with self._lock:
            cached = self._cached.get(window_minutes)
            if cached is not None and now - cached[0] < self.cache_seconds:
                return {**cached[1], "cache": "HIT"}

        snapshot = self._load(window_minutes)
        with self._lock:
            self._cached[window_minutes] = (now, snapshot)
        return {**snapshot, "cache": "MISS"}

    def _load(self, window_minutes: int) -> dict[str, object]:
        generated_at = datetime.now(UTC)
        period_start = generated_at - timedelta(minutes=window_minutes)
        parameters = {"period_start": period_start}
        with self.engine.connect() as connection:
            summary = (
                connection.execute(
                    text(
                        """WITH job_costs AS (
                          SELECT j.job_id, j.status, j.created_at, j.updated_at,
                                 COALESCE(u.cost_usd_micros, m.fallback_cost_usd_micros, 0)
                                   AS cost_usd_micros,
                                 COALESCE(u.cost_basis, 'ESTIMATED') AS cost_basis
                          FROM render_jobs j
                          JOIN render_quotes q ON q.quote_id=j.quote_id
                          LEFT JOIN ai_providers p ON p.code=q.provider
                          LEFT JOIN ai_models m ON m.provider_id=p.provider_id
                            AND m.api_model_id=q.model_version AND m.region=q.provider_region
                          LEFT JOIN model_usage_costs u ON u.job_id=j.job_id
                          WHERE j.created_at >= :period_start
                        )
                        SELECT count(*) total_try_ons,
                               count(*) FILTER (WHERE status='PENDING') queued_try_ons,
                               count(*) FILTER (WHERE status='PROCESSING') processing_try_ons,
                               count(*) FILTER (WHERE status='DELIVERED') successful_try_ons,
                               count(*) FILTER (WHERE status='FAILED') failed_try_ons,
                               COALESCE(round(avg(extract(epoch FROM (updated_at-created_at))
                                 * 1000) FILTER (WHERE status IN ('DELIVERED','FAILED'))), 0)
                                 average_generation_time_ms,
                               COALESCE(round(avg(cost_usd_micros)), 0) average_cost_usd_micros,
                               COALESCE(sum(cost_usd_micros), 0) total_cost_usd_micros,
                               count(*) FILTER (WHERE cost_basis='ACTUAL') actual_cost_try_ons
                        FROM job_costs"""
                    ),
                    parameters,
                )
                .mappings()
                .one()
            )
            rows = connection.execute(
                text(
                    """SELECT j.job_id, j.status, j.error_code, j.created_at, j.updated_at,
                              round(extract(epoch FROM (j.updated_at-j.created_at))*1000)
                                AS generation_time_ms,
                              q.provider, q.model_version,
                              COALESCE(usage.cost_usd_micros, model.fallback_cost_usd_micros, 0)
                                AS cost_usd_micros,
                              COALESCE(usage.cost_basis, 'ESTIMATED') AS cost_basis
                       FROM render_jobs j
                       JOIN render_quotes q ON q.quote_id=j.quote_id
                       LEFT JOIN ai_providers provider ON provider.code=q.provider
                       LEFT JOIN ai_models model ON model.provider_id=provider.provider_id
                         AND model.api_model_id=q.model_version AND model.region=q.provider_region
                       LEFT JOIN model_usage_costs usage ON usage.job_id=j.job_id
                       WHERE j.created_at >= :period_start
                       ORDER BY j.created_at DESC LIMIT 50"""
                ),
                parameters,
            ).mappings()
            items = [dict(row) for row in rows]

        actual_count = int(summary["actual_cost_try_ons"])
        total = int(summary["total_try_ons"])
        cost_basis = "ACTUAL" if total and actual_count == total else "ESTIMATED"
        return {
            "generated_at": generated_at,
            "window_minutes": window_minutes,
            "currency": "USD",
            "cost_basis": cost_basis,
            "summary": {key: value for key, value in summary.items()},
            "try_ons": items,
        }
