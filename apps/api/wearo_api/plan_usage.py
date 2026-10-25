from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, text

BUSINESS_REPORTING_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class UsageSnapshot:
    plan_code: str
    tokens_purchased: int
    token_balance: int
    tokens_used: int
    preview_limit: int | None
    previews_used: int
    previews_today: int
    previews_remaining: int | None
    action_code: str | None
    action_cost: int | None
    balance_after_action: int | None
    estimated_previews: int | None
    unique_participants: int
    provider_input_tokens: int
    provider_output_tokens: int
    provider_total_tokens: int
    average_tokens_per_preview: float | None
    average_previews_per_day: float | None
    average_previews_per_hour: float | None


def usage_snapshot(
    *,
    plan_code: str,
    token_balance: int,
    tokens_used: int,
    preview_limit: int | None,
    previews_used: int,
    previews_today: int = 0,
    action_code: str | None = None,
    action_cost: int | None = None,
    unique_participants: int = 0,
    provider_input_tokens: int = 0,
    provider_output_tokens: int = 0,
    provider_total_tokens: int = 0,
    tokens_purchased: int = 0,
    reporting_hours: float | None = None,
) -> UsageSnapshot:
    remaining = None if preview_limit is None else max(preview_limit - previews_used, 0)
    after = None if action_cost is None else max(token_balance - action_cost, 0)
    average_tokens = tokens_used / previews_used if previews_used > 0 else None
    estimates = int(token_balance // average_tokens) if average_tokens else None
    average_hourly = previews_used / reporting_hours if reporting_hours else None
    average_daily = average_hourly * 24 if average_hourly is not None else None
    return UsageSnapshot(
        plan_code=plan_code,
        tokens_purchased=tokens_purchased,
        token_balance=token_balance,
        tokens_used=tokens_used,
        preview_limit=preview_limit,
        previews_used=previews_used,
        previews_today=previews_today,
        previews_remaining=remaining,
        action_code=action_code,
        action_cost=action_cost,
        balance_after_action=after,
        estimated_previews=estimates,
        unique_participants=unique_participants,
        provider_input_tokens=provider_input_tokens,
        provider_output_tokens=provider_output_tokens,
        provider_total_tokens=provider_total_tokens,
        average_tokens_per_preview=average_tokens,
        average_previews_per_day=average_daily,
        average_previews_per_hour=average_hourly,
    )


class PostgresPlanUsage:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def for_account(
        self,
        account_id: UUID,
        *,
        tenant_id: UUID | None = None,
        action_code: str = "TRY_ON",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> UsageSnapshot:
        current = datetime.now(UTC)
        reporting_today = current.astimezone(BUSINESS_REPORTING_TIMEZONE).date()
        today_start = datetime.combine(
            reporting_today, time.min, BUSINESS_REPORTING_TIMEZONE
        ).astimezone(UTC)
        today_end = today_start + timedelta(days=1)
        period_start = (
            datetime.combine(date_from, time.min, BUSINESS_REPORTING_TIMEZONE).astimezone(UTC)
            if date_from
            else None
        )
        period_end = (
            datetime.combine(
                date_to + timedelta(days=1), time.min, BUSINESS_REPORTING_TIMEZONE
            ).astimezone(UTC)
            if date_to
            else None
        )
        with self.engine.connect() as connection:
            plan = (
                connection.execute(
                    text(
                        """
                    SELECT plan_code, preview_limit
                    FROM plan_assignments
                    WHERE account_id = :account
                      AND tenant_id IS NOT DISTINCT FROM :tenant
                      AND effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY effective_from DESC LIMIT 1
                    """
                    ),
                    {"account": account_id, "tenant": tenant_id, "now": current},
                )
                .mappings()
                .one_or_none()
            )
            ledger = (
                connection.execute(
                    text(
                        """
                    SELECT COALESCE(sum(amount), 0) AS balance,
                           COALESCE(sum(amount) FILTER (
                               WHERE entry_type = 'CREDIT' AND amount > 0
                           ), 0) AS purchased,
                           COALESCE(-sum(amount) FILTER (
                               WHERE entry_type = 'DEBIT' AND amount < 0
                                 AND (CAST(:period_start AS timestamptz) IS NULL
                                      OR created_at >= :period_start)
                                 AND (CAST(:period_end AS timestamptz) IS NULL
                                      OR created_at < :period_end)
                           ), 0) AS used
                    FROM ledger_entries
                    WHERE account_id = :account
                      AND tenant_id IS NOT DISTINCT FROM :tenant
                    """
                    ),
                    {
                        "account": account_id,
                        "tenant": tenant_id,
                        "period_start": period_start,
                        "period_end": period_end,
                    },
                )
                .mappings()
                .one()
            )
            tokens_used = int(ledger["used"])
            price = connection.execute(
                text(
                    """
                    SELECT token_cost FROM price_versions
                    WHERE action_code = :action AND effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY effective_from DESC LIMIT 1
                    """
                ),
                {"action": action_code, "now": current},
            ).scalar_one_or_none()
            if tenant_id is None:
                consumer_previews = (
                    connection.execute(
                        text(
                            """
                            SELECT COALESCE(sum(successful_generations), 0) AS selected,
                                   COALESCE(sum(successful_generations) FILTER (
                                     WHERE usage_date_ist = :reporting_today
                                   ), 0) AS today
                            FROM generation_daily_usage WHERE account_id = :account
                              AND (CAST(:date_from AS date) IS NULL
                                   OR usage_date_ist >= :date_from)
                              AND (CAST(:date_to AS date) IS NULL
                                   OR usage_date_ist <= :date_to)
                            """
                        ),
                        {
                            "account": account_id,
                            "date_from": date_from,
                            "date_to": date_to,
                            "reporting_today": reporting_today,
                        },
                    )
                    .mappings()
                    .one()
                )
                previews_used = int(consumer_previews["selected"])
                previews_today = int(consumer_previews["today"])
            else:
                delivered_usage = (
                    connection.execute(
                        text(
                            """
                            SELECT count(*) FILTER (
                                     WHERE (CAST(:period_start AS timestamptz) IS NULL
                                            OR job.created_at >= :period_start)
                                       AND (CAST(:period_end AS timestamptz) IS NULL
                                            OR job.created_at < :period_end)
                                   ) AS previews_used,
                                   count(*) FILTER (
                                     WHERE job.created_at >= :today_start
                                       AND job.created_at < :today_end
                                   ) AS previews_today,
                                   count(DISTINCT session.participant_id) FILTER (
                                     WHERE (CAST(:period_start AS timestamptz) IS NULL
                                            OR job.created_at >= :period_start)
                                       AND (CAST(:period_end AS timestamptz) IS NULL
                                            OR job.created_at < :period_end)
                                   )
                                     AS unique_participants,
                                   COALESCE(sum(usage.token_cost) FILTER (
                                     WHERE (CAST(:period_start AS timestamptz) IS NULL
                                            OR job.created_at >= :period_start)
                                       AND (CAST(:period_end AS timestamptz) IS NULL
                                            OR job.created_at < :period_end)
                                   ), 0) AS tokens_used
                            FROM business_sponsored_tryons sponsored
                            JOIN business_sponsored_sessions session
                              ON session.session_id = sponsored.session_id
                             AND session.business_account_id = sponsored.business_account_id
                             AND session.tenant_id = sponsored.tenant_id
                            JOIN billable_usage_records usage
                              ON usage.usage_id = sponsored.usage_id
                             AND usage.account_id = sponsored.business_account_id
                             AND usage.tenant_id = sponsored.tenant_id
                            JOIN render_jobs job
                              ON job.account_id = session.consumer_account_id
                             AND job.tenant_id IS NULL
                             AND job.idempotency_key = substring(sponsored.request_key FROM 11)
                            WHERE sponsored.business_account_id = :account
                              AND sponsored.tenant_id = :tenant
                              AND usage.action_code = :action
                              AND job.status = 'DELIVERED'
                            """
                        ),
                        {
                            "account": account_id,
                            "tenant": tenant_id,
                            "action": action_code,
                            "today_start": today_start,
                            "today_end": today_end,
                            "period_start": period_start,
                            "period_end": period_end,
                        },
                    )
                    .mappings()
                    .one()
                )
                previews_used = int(delivered_usage["previews_used"])
                previews_today = int(delivered_usage["previews_today"])
                unique_participants = int(delivered_usage["unique_participants"])
                tokens_used = int(delivered_usage["tokens_used"])
            if tenant_id is None:
                unique_participants = 0
            if tenant_id is None:
                provider_usage = (
                    connection.execute(
                        text(
                            """
                            SELECT
                              COALESCE(
                                sum((provider_usage->>'input_tokens')::bigint), 0
                              ) AS input,
                              COALESCE(
                                sum((provider_usage->>'output_tokens')::bigint), 0
                              ) AS output,
                              COALESCE(
                                sum((provider_usage->>'total_tokens')::bigint), 0
                              ) AS total
                            FROM render_results
                            WHERE account_id = :account
                              AND (CAST(:period_start AS timestamptz) IS NULL
                                   OR created_at >= :period_start)
                              AND (CAST(:period_end AS timestamptz) IS NULL
                                   OR created_at < :period_end)
                            """
                        ),
                        {
                            "account": account_id,
                            "period_start": period_start,
                            "period_end": period_end,
                        },
                    )
                    .mappings()
                    .one()
                )
            else:
                provider_usage = (
                    connection.execute(
                        text(
                            """
                            SELECT
                              COALESCE(
                                sum((result.provider_usage->>'input_tokens')::bigint), 0
                              ) AS input,
                              COALESCE(
                                sum((result.provider_usage->>'output_tokens')::bigint), 0
                              ) AS output,
                              COALESCE(
                                sum((result.provider_usage->>'total_tokens')::bigint), 0
                              ) AS total
                            FROM business_sponsored_tryons sponsored
                            JOIN business_sponsored_sessions session
                              ON session.session_id = sponsored.session_id
                             AND session.business_account_id = sponsored.business_account_id
                             AND session.tenant_id = sponsored.tenant_id
                            JOIN render_jobs job
                              ON job.account_id = session.consumer_account_id
                             AND job.tenant_id IS NULL
                             AND job.idempotency_key = substring(sponsored.request_key FROM 11)
                            JOIN render_results result ON result.job_id = job.job_id
                            WHERE sponsored.business_account_id = :account
                              AND sponsored.tenant_id = :tenant
                              AND (CAST(:period_start AS timestamptz) IS NULL
                                   OR job.created_at >= :period_start)
                              AND (CAST(:period_end AS timestamptz) IS NULL
                                   OR job.created_at < :period_end)
                            """
                        ),
                        {
                            "account": account_id,
                            "tenant": tenant_id,
                            "period_start": period_start,
                            "period_end": period_end,
                        },
                    )
                    .mappings()
                    .one()
                )
        default_plan = "FREE_BETA" if tenant_id is None else "BUSINESS_UNASSIGNED"
        return usage_snapshot(
            plan_code=plan["plan_code"] if plan else default_plan,
            token_balance=int(ledger["balance"]),
            tokens_used=tokens_used,
            preview_limit=plan["preview_limit"] if plan else (3 if tenant_id is None else None),
            previews_used=previews_used,
            previews_today=previews_today,
            action_code=action_code if price is not None else None,
            action_cost=int(price) if price is not None else None,
            unique_participants=unique_participants,
            provider_input_tokens=int(provider_usage["input"]),
            provider_output_tokens=int(provider_usage["output"]),
            provider_total_tokens=int(provider_usage["total"]),
            tokens_purchased=int(ledger["purchased"]),
            reporting_hours=(
                max((period_end - period_start).total_seconds() / 3600, 1)
                if period_start is not None and period_end is not None
                else None
            ),
        )
