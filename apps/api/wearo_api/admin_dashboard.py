from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import Engine, text

from .admin_organizations import BUSINESS_TYPES
from .plan_usage import BUSINESS_REPORTING_TIMEZONE


class AdminDashboardError(ValueError):
    pass


@dataclass(frozen=True)
class OrganizationUsage:
    total_try_ons: int
    successful_try_ons: int
    failed_try_ons: int
    tokens_consumed: int


def combine_organization_usage(records: Iterable[OrganizationUsage]) -> dict[str, int | float]:
    items = tuple(records)
    total = sum(item.total_try_ons for item in items)
    return {
        "total_try_ons": total,
        "successful_try_ons": sum(item.successful_try_ons for item in items),
        "failed_try_ons": sum(item.failed_try_ons for item in items),
        "total_tokens_consumed": sum(item.tokens_consumed for item in items),
        "average_try_ons_per_organization": round(total / len(items), 2) if items else 0.0,
    }


class PostgresAdminDashboard:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def metrics(
        self,
        *,
        date_from: date,
        date_to: date,
        tenant_id: UUID | None = None,
        business_type: str | None = None,
    ) -> dict[str, int | float]:
        if date_from > date_to:
            raise AdminDashboardError("Start date must not be after end date.")
        if (date_to - date_from).days > 366:
            raise AdminDashboardError("Dashboard date range cannot exceed 367 days.")
        normalized_type = business_type.strip().upper() if business_type else None
        if normalized_type and normalized_type not in BUSINESS_TYPES:
            raise AdminDashboardError("Unsupported business type filter.")
        period_start = datetime.combine(
            date_from, time.min, BUSINESS_REPORTING_TIMEZONE
        ).astimezone(UTC)
        period_end = datetime.combine(
            date_to + timedelta(days=1), time.min, BUSINESS_REPORTING_TIMEZONE
        ).astimezone(UTC)
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    WITH filtered_organizations AS (
                      SELECT t.tenant_id, t.account_id, t.try_on_status
                      FROM business_tenants t
                      JOIN business_profiles p
                        ON p.tenant_id=t.tenant_id AND p.account_id=t.account_id
                      WHERE (CAST(:tenant AS uuid) IS NULL OR t.tenant_id=:tenant)
                        AND (CAST(:business_type AS varchar) IS NULL
                             OR p.operating_profile=CAST(:business_type AS varchar))
                    ), usage AS (
                      SELECT sponsored.tenant_id, job.status, usage.token_cost,
                             session.consumer_account_id
                      FROM filtered_organizations organization
                      JOIN business_sponsored_tryons sponsored
                        ON sponsored.tenant_id=organization.tenant_id
                       AND sponsored.business_account_id=organization.account_id
                      JOIN business_sponsored_sessions session
                        ON session.session_id=sponsored.session_id
                       AND session.tenant_id=sponsored.tenant_id
                       AND session.business_account_id=sponsored.business_account_id
                      JOIN billable_usage_records usage
                        ON usage.usage_id=sponsored.usage_id
                       AND usage.account_id=sponsored.business_account_id
                       AND usage.tenant_id=sponsored.tenant_id
                      JOIN render_jobs job ON job.job_id=sponsored.render_job_id
                      WHERE usage.action_code='TRY_ON'
                        AND job.created_at >= :period_start AND job.created_at < :period_end
                        AND job.status IN ('DELIVERED', 'FAILED')
                    )
                    SELECT (SELECT count(*) FROM filtered_organizations) total_organizations,
                           (SELECT count(*) FROM filtered_organizations
                            WHERE try_on_status='ACTIVE') active_organizations,
                           count(DISTINCT consumer_account_id) total_registered_consumers,
                           count(*) total_try_ons,
                           count(*) FILTER (WHERE status='DELIVERED') successful_try_ons,
                           count(*) FILTER (WHERE status='FAILED') failed_try_ons,
                           COALESCE(sum(token_cost) FILTER (WHERE status='DELIVERED'), 0)
                             total_tokens_consumed
                    FROM usage
                    """
                ),
                {
                    "tenant": tenant_id,
                    "business_type": normalized_type,
                    "period_start": period_start,
                    "period_end": period_end,
                },
            ).mappings().one()
        result: dict[str, int | float] = {str(key): int(value) for key, value in row.items()}
        organizations = int(result["total_organizations"])
        result["average_try_ons_per_organization"] = (
            round(int(result["total_try_ons"]) / organizations, 2) if organizations else 0.0
        )
        return result
