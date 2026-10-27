from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import Engine, text

from .admin_organizations import BUSINESS_TYPES
from .plan_usage import BUSINESS_REPORTING_TIMEZONE


class AdminUsageAnalyticsError(ValueError):
    pass


@dataclass(frozen=True)
class TokenActivity:
    purchased: int
    consumed: int
    manually_adjusted: int
    remaining: int


def reconcile_token_activity(
    *, purchased: int, consumed: int, manually_adjusted: int, opening_tokens: int = 0
) -> TokenActivity:
    return TokenActivity(
        purchased=purchased,
        consumed=consumed,
        manually_adjusted=manually_adjusted,
        remaining=opening_tokens + purchased - consumed + manually_adjusted,
    )


class PostgresAdminUsageAnalytics:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _period(date_from: date, date_to: date) -> tuple[datetime, datetime]:
        if date_from > date_to:
            raise AdminUsageAnalyticsError("Start date must not be after end date.")
        if (date_to - date_from).days > 366:
            raise AdminUsageAnalyticsError("Analytics date range cannot exceed 367 days.")
        start = datetime.combine(date_from, time.min, BUSINESS_REPORTING_TIMEZONE).astimezone(UTC)
        end = datetime.combine(
            date_to + timedelta(days=1), time.min, BUSINESS_REPORTING_TIMEZONE
        ).astimezone(UTC)
        return start, end

    def organizations(
        self,
        *,
        date_from: date,
        date_to: date,
        tenant_id: UUID | None = None,
        business_type: str | None = None,
    ) -> dict[str, object]:
        start, end = self._period(date_from, date_to)
        normalized_type = business_type.strip().upper() if business_type else None
        if normalized_type and normalized_type not in BUSINESS_TYPES:
            raise AdminUsageAnalyticsError("Unsupported business type filter.")
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    WITH organizations AS (
                      SELECT t.tenant_id, t.account_id, p.display_name, p.operating_profile
                      FROM business_tenants t JOIN business_profiles p
                        ON p.tenant_id=t.tenant_id AND p.account_id=t.account_id
                      WHERE (CAST(:tenant AS uuid) IS NULL OR t.tenant_id=:tenant)
                        AND (CAST(:business_type AS varchar) IS NULL
                             OR p.operating_profile=CAST(:business_type AS varchar))
                    ), attempts AS (
                      SELECT DISTINCT ON (usage.account_id, usage.request_key)
                             usage.account_id, usage.tenant_id, usage.request_key,
                             usage.token_cost, job.status, job.created_at
                      FROM billable_usage_records usage
                      JOIN business_sponsored_tryons sponsored
                        ON sponsored.usage_id=usage.usage_id
                       AND sponsored.business_account_id=usage.account_id
                       AND sponsored.tenant_id=usage.tenant_id
                      JOIN render_jobs job ON job.job_id=sponsored.render_job_id
                      WHERE usage.action_code='TRY_ON'
                        AND job.created_at >= :period_start AND job.created_at < :period_end
                      ORDER BY usage.account_id, usage.request_key, job.created_at DESC
                    ), usage_totals AS (
                      SELECT account_id, tenant_id, count(*) total_try_ons,
                             count(*) FILTER (WHERE status='DELIVERED') successful_try_ons,
                             count(*) FILTER (WHERE status='FAILED') failed_try_ons,
                             COALESCE(sum(token_cost) FILTER (WHERE status='DELIVERED'), 0)
                               tokens_consumed
                      FROM attempts GROUP BY account_id, tenant_id
                    ), payments AS (
                      SELECT account_id, COALESCE(sum(tokens_credited), 0) tokens_purchased
                      FROM payment_receipts
                      WHERE issued_at >= :period_start AND issued_at < :period_end
                      GROUP BY account_id
                    ), adjustments AS (
                      SELECT account_id, tenant_id, COALESCE(sum(amount), 0) manually_adjusted
                      FROM ledger_entries
                      WHERE operation_key LIKE 'admin-adjustment:%'
                        AND created_at >= :period_start AND created_at < :period_end
                      GROUP BY account_id, tenant_id
                    ), balances AS (
                      SELECT account_id, tenant_id, COALESCE(sum(amount), 0) remaining_tokens
                      FROM ledger_entries GROUP BY account_id, tenant_id
                    )
                    SELECT organization.tenant_id,
                           organization.display_name AS organization_name,
                           organization.operating_profile AS business_type,
                           COALESCE(usage.total_try_ons, 0) total_try_ons,
                           COALESCE(usage.successful_try_ons, 0) successful_try_ons,
                           COALESCE(usage.failed_try_ons, 0) failed_try_ons,
                           COALESCE(payment.tokens_purchased, 0) tokens_purchased,
                           COALESCE(usage.tokens_consumed, 0) tokens_consumed,
                           COALESCE(adjustment.manually_adjusted, 0) manually_adjusted,
                           COALESCE(balance.remaining_tokens, 0) remaining_tokens
                    FROM organizations organization
                    LEFT JOIN usage_totals usage
                      ON usage.account_id=organization.account_id
                     AND usage.tenant_id=organization.tenant_id
                    LEFT JOIN payments payment ON payment.account_id=organization.account_id
                    LEFT JOIN adjustments adjustment
                      ON adjustment.account_id=organization.account_id
                     AND adjustment.tenant_id=organization.tenant_id
                    LEFT JOIN balances balance ON balance.account_id=organization.account_id
                     AND balance.tenant_id=organization.tenant_id
                    ORDER BY total_try_ons DESC, organization.display_name
                    """
                ),
                {
                    "business_type": normalized_type,
                    "tenant": tenant_id,
                    "period_start": start,
                    "period_end": end,
                },
            ).mappings()
            organizations = [dict(row) for row in rows]
        return {"organizations": organizations, "most_active": organizations[:5]}

    def history(
        self, tenant_id: UUID, *, date_from: date, date_to: date
    ) -> dict[str, object]:
        start, end = self._period(date_from, date_to)
        with self.engine.connect() as connection:
            organization = connection.execute(
                text("SELECT account_id FROM business_tenants WHERE tenant_id=:tenant"),
                {"tenant": tenant_id},
            ).mappings().one_or_none()
            if organization is None:
                raise AdminUsageAnalyticsError("Organization not found.")
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (usage.request_key)
                           usage.request_key, job.created_at, job.status,
                           CASE WHEN job.status='DELIVERED' THEN usage.token_cost ELSE 0 END
                             AS tokens_consumed
                    FROM billable_usage_records usage
                    JOIN business_sponsored_tryons sponsored
                      ON sponsored.usage_id=usage.usage_id
                     AND sponsored.business_account_id=usage.account_id
                     AND sponsored.tenant_id=usage.tenant_id
                    JOIN render_jobs job ON job.job_id=sponsored.render_job_id
                    WHERE usage.account_id=:account AND usage.tenant_id=:tenant
                      AND usage.action_code='TRY_ON'
                      AND job.created_at >= :period_start AND job.created_at < :period_end
                    ORDER BY usage.request_key, job.created_at DESC
                    """
                ),
                {
                    "account": organization["account_id"],
                    "tenant": tenant_id,
                    "period_start": start,
                    "period_end": end,
                },
            ).mappings()
            items = [dict(row) for row in rows]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return {"tenant_id": tenant_id, "items": items}
