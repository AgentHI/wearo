from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import Engine, text

from .admin_organizations import BUSINESS_TYPES
from .plan_usage import BUSINESS_REPORTING_TIMEZONE


class AdminOperationsError(ValueError):
    pass


def operation_metrics(successful: int, failed: int, duration_ms: int) -> dict[str, int | float]:
    completed = successful + failed
    return {
        "success_rate": round(successful / completed * 100, 2) if completed else 0.0,
        "average_processing_time_ms": round(duration_ms / completed) if completed else 0,
    }


class PostgresAdminOperations:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _filters(
        date_from: date, date_to: date, business_type: str | None
    ) -> tuple[datetime, datetime, str | None]:
        if date_from > date_to:
            raise AdminOperationsError("Start date must not be after end date.")
        if (date_to - date_from).days > 366:
            raise AdminOperationsError("Operations date range cannot exceed 367 days.")
        normalized = business_type.strip().upper() if business_type else None
        if normalized and normalized not in BUSINESS_TYPES:
            raise AdminOperationsError("Unsupported business type filter.")
        start = datetime.combine(date_from, time.min, BUSINESS_REPORTING_TIMEZONE).astimezone(UTC)
        end = datetime.combine(
            date_to + timedelta(days=1), time.min, BUSINESS_REPORTING_TIMEZONE
        ).astimezone(UTC)
        return start, end, normalized

    def list(
        self,
        *,
        date_from: date,
        date_to: date,
        tenant_id: UUID | None = None,
        business_type: str | None = None,
    ) -> dict[str, object]:
        start, end, normalized = self._filters(date_from, date_to, business_type)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT j.job_id, j.tenant_id, p.display_name AS organization_name,
                              p.operating_profile AS business_type, j.status, j.error_code,
                              j.created_at, j.updated_at,
                              CASE WHEN j.status IN ('DELIVERED', 'FAILED', 'CANCELLED')
                                THEN round(extract(epoch FROM (j.updated_at-j.created_at))*1000)
                                ELSE NULL END processing_time_ms,
                              q.provider, q.model_version, q.provider_region,
                              attempt.attempt_number, attempt.status AS attempt_status,
                              attempt.provider_attempt_ref
                       FROM render_jobs j
                       JOIN business_profiles p ON p.tenant_id=j.tenant_id
                                                AND p.account_id=j.account_id
                       JOIN render_quotes q ON q.quote_id=j.quote_id
                                           AND q.account_id=j.account_id
                       LEFT JOIN LATERAL (
                         SELECT attempt_number, status, provider_attempt_ref
                         FROM render_attempts a WHERE a.job_id=j.job_id
                         ORDER BY attempt_number DESC LIMIT 1
                       ) attempt ON true
                       WHERE j.created_at >= :start AND j.created_at < :end
                         AND (CAST(:tenant AS uuid) IS NULL OR j.tenant_id=:tenant)
                         AND (CAST(:business_type AS varchar) IS NULL
                              OR p.operating_profile=CAST(:business_type AS varchar))
                       ORDER BY j.created_at DESC"""
                ),
                {
                    "start": start,
                    "end": end,
                    "tenant": tenant_id,
                    "business_type": normalized,
                },
            ).mappings()
            items = [dict(row) for row in rows]
        successful = sum(item["status"] == "DELIVERED" for item in items)
        failed = sum(item["status"] == "FAILED" for item in items)
        duration = sum(
            int(item["processing_time_ms"] or 0)
            for item in items
            if item["status"] in {"DELIVERED", "FAILED"}
        )
        reasons: dict[str, int] = {}
        for item in items:
            if item["error_code"]:
                code = str(item["error_code"])
                reasons[code] = reasons.get(code, 0) + 1
        return {
            "summary": {
                "total_requests": len(items),
                "successful_requests": successful,
                "failed_requests": failed,
                **operation_metrics(successful, failed, duration),
            },
            "failure_reasons": [
                {"reason": reason, "count": count}
                for reason, count in sorted(reasons.items(), key=lambda value: -value[1])
            ],
            "requests": items,
            "privacy": "Operational metadata only; customer images are not included.",
        }

    def detail(self, job_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """SELECT j.job_id, j.tenant_id, p.display_name AS organization_name,
                              j.status, j.error_code, j.created_at, j.updated_at,
                              q.provider, q.model_version, q.provider_region,
                              a.attempt_number, a.status AS attempt_status,
                              a.started_at, a.finished_at, a.provider_attempt_ref
                       FROM render_jobs j
                       JOIN business_profiles p ON p.tenant_id=j.tenant_id
                                                AND p.account_id=j.account_id
                       JOIN render_quotes q ON q.quote_id=j.quote_id
                       LEFT JOIN render_attempts a ON a.job_id=j.job_id
                       WHERE j.job_id=:job ORDER BY a.attempt_number"""
                ),
                {"job": job_id},
            ).mappings()
            attempts = [dict(item) for item in row]
        if not attempts:
            raise AdminOperationsError("Try-on request not found.")
        first = attempts[0]
        return {
            "job_id": first["job_id"],
            "tenant_id": first["tenant_id"],
            "organization_name": first["organization_name"],
            "status": first["status"],
            "error_code": first["error_code"],
            "created_at": first["created_at"],
            "updated_at": first["updated_at"],
            "provider": first["provider"],
            "model_version": first["model_version"],
            "provider_region": first["provider_region"],
            "attempts": [
                {
                    key: item[key]
                    for key in (
                        "attempt_number",
                        "attempt_status",
                        "started_at",
                        "finished_at",
                        "provider_attempt_ref",
                    )
                }
                for item in attempts
                if item["attempt_number"] is not None
            ],
            "images_exposed": False,
        }
