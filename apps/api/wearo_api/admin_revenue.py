from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import Engine, text

from .plan_usage import BUSINESS_REPORTING_TIMEZONE


class AdminRevenueError(ValueError):
    pass


@dataclass(frozen=True)
class RevenueTotals:
    received_minor: int
    subscription_minor: int
    token_minor: int
    pending_minor: int
    estimated_ai_cost_minor: int
    actual_ai_cost_minor: int

    @property
    def estimated_gross_margin_minor(self) -> int:
        return self.received_minor - self.estimated_ai_cost_minor

    @property
    def estimated_gross_margin_percent(self) -> float:
        if not self.received_minor:
            return 0.0
        return round(self.estimated_gross_margin_minor / self.received_minor * 100, 2)


class PostgresAdminRevenue:
    def __init__(self, engine: Engine, estimated_ai_cost_minor: int = 0) -> None:
        if estimated_ai_cost_minor < 0:
            raise AdminRevenueError("Estimated AI cost must not be negative.")
        self.engine = engine
        self.estimated_ai_cost_minor = estimated_ai_cost_minor

    def metrics(
        self, *, date_from: date, date_to: date, tenant_id: UUID | None = None
    ) -> dict[str, object]:
        if date_from > date_to:
            raise AdminRevenueError("Start date must not be after end date.")
        if (date_to - date_from).days > 366:
            raise AdminRevenueError("Revenue date range cannot exceed 367 days.")
        start = datetime.combine(date_from, time.min, BUSINESS_REPORTING_TIMEZONE).astimezone(UTC)
        end = datetime.combine(
            date_to + timedelta(days=1), time.min, BUSINESS_REPORTING_TIMEZONE
        ).astimezone(UTC)
        parameters = {"tenant": tenant_id, "start": start, "end": end}
        with self.engine.connect() as connection:
            revenue = (
                connection.execute(
                    text(
                        """SELECT
                         COALESCE(sum(i.subtotal_minor) FILTER (
                           WHERE o.state='CONFIRMED'
                             AND r.issued_at >= :start AND r.issued_at < :end), 0)
                           received_minor,
                         COALESCE(sum(i.subtotal_minor) FILTER (
                           WHERE o.state='CONFIRMED' AND o.revenue_type='SUBSCRIPTION'
                             AND r.issued_at >= :start AND r.issued_at < :end), 0)
                           subscription_minor,
                         COALESCE(sum(i.subtotal_minor) FILTER (
                           WHERE o.state='CONFIRMED' AND o.revenue_type='TOKEN_PURCHASE'
                             AND r.issued_at >= :start AND r.issued_at < :end), 0)
                           token_minor,
                         COALESCE(sum(o.amount_minor) FILTER (
                           WHERE o.state IN ('CREATED', 'PENDING')
                             AND o.created_at >= :start AND o.created_at < :end), 0)
                           pending_minor
                       FROM payment_orders o
                       LEFT JOIN invoices i ON i.payment_order_id=o.payment_order_id
                       LEFT JOIN payment_receipts r ON r.payment_order_id=o.payment_order_id
                       WHERE (CAST(:tenant AS uuid) IS NULL OR o.tenant_id=:tenant)
                       """
                    ),
                    parameters,
                )
                .mappings()
                .one()
            )
            costs = (
                connection.execute(
                    text(
                        """SELECT count(*) attempt_count,
                              COALESCE(sum(provider_cost_minor), 0) actual_cost_minor,
                              count(provider_cost_minor) recorded_attempt_count
                       FROM render_attempts
                       WHERE (CAST(:tenant AS uuid) IS NULL OR tenant_id=:tenant)
                         AND started_at >= :start AND started_at < :end"""
                    ),
                    parameters,
                )
                .mappings()
                .one()
            )
        totals = RevenueTotals(
            received_minor=int(revenue["received_minor"]),
            subscription_minor=int(revenue["subscription_minor"]),
            token_minor=int(revenue["token_minor"]),
            pending_minor=int(revenue["pending_minor"]),
            estimated_ai_cost_minor=int(costs["attempt_count"]) * self.estimated_ai_cost_minor,
            actual_ai_cost_minor=int(costs["actual_cost_minor"]),
        )
        return {
            "currency": "INR",
            "total_revenue_minor": totals.received_minor,
            "received_revenue_minor": totals.received_minor,
            "monthly_subscription_revenue_minor": totals.subscription_minor,
            "token_purchase_revenue_minor": totals.token_minor,
            "pending_collections_minor": totals.pending_minor,
            "estimated_ai_generation_cost_minor": totals.estimated_ai_cost_minor,
            "actual_recorded_ai_cost_minor": totals.actual_ai_cost_minor,
            "actual_cost_attempts": int(costs["recorded_attempt_count"]),
            "total_generation_attempts": int(costs["attempt_count"]),
            "estimated_cost_per_attempt_minor": self.estimated_ai_cost_minor,
            "estimated_gross_margin_minor": totals.estimated_gross_margin_minor,
            "estimated_gross_margin_percent": totals.estimated_gross_margin_percent,
            "cost_basis": "CONFIGURED_ESTIMATE",
        }
