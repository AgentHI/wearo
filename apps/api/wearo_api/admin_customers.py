from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Literal

from sqlalchemy import Engine, text

CustomerStatus = Literal[
    "ACTIVE", "TRIAL", "PENDING_PAYMENT", "PAUSED", "CANCELLED", "EXPIRED"
]
CUSTOMER_STATUSES = frozenset(
    {"ACTIVE", "TRIAL", "PENDING_PAYMENT", "PAUSED", "CANCELLED", "EXPIRED"}
)


class AdminCustomerError(ValueError):
    pass


def customer_statuses(
    *,
    subscription_state: str,
    payment_pending: bool,
    try_on_status: str,
) -> tuple[CustomerStatus, ...]:
    statuses: list[CustomerStatus] = []
    if subscription_state in {"ACTIVE", "TRIAL"} and try_on_status == "ACTIVE":
        statuses.append("ACTIVE")
    if subscription_state == "TRIAL":
        statuses.append("TRIAL")
    if payment_pending or subscription_state == "PAYMENT_DUE":
        statuses.append("PENDING_PAYMENT")
    if try_on_status == "PAUSED" or subscription_state == "PAUSED":
        statuses.append("PAUSED")
    if subscription_state == "CANCELLED":
        statuses.append("CANCELLED")
    if subscription_state == "EXPIRED":
        statuses.append("EXPIRED")
    return tuple(statuses)


def customer_counts(customers: Iterable[tuple[CustomerStatus, ...]]) -> dict[str, int]:
    items = tuple(customers)
    counts = Counter(status for statuses in items for status in statuses)
    return {
        "total": len(items),
        "active": counts["ACTIVE"],
        "trial": counts["TRIAL"],
        "pending_payment": counts["PENDING_PAYMENT"],
        "paused": counts["PAUSED"],
        "cancelled": counts["CANCELLED"],
        "expired": counts["EXPIRED"],
    }


class PostgresAdminCustomers:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list(self, *, status: str | None = None) -> dict[str, object]:
        normalized = status.strip().upper() if status else None
        if normalized and normalized not in CUSTOMER_STATUSES:
            raise AdminCustomerError("Unsupported customer status filter.")
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT t.tenant_id, p.display_name AS customer_name,
                           p.operating_profile AS business_type, t.try_on_status,
                           subscription.plan_code, subscription.state AS subscription_state,
                           EXISTS (
                             SELECT 1 FROM payment_orders payment
                             WHERE payment.account_id=t.account_id
                               AND payment.tenant_id=t.tenant_id
                               AND payment.state IN ('CREATED', 'PENDING')
                           ) AS payment_pending
                    FROM business_tenants t
                    JOIN business_profiles p
                      ON p.tenant_id=t.tenant_id AND p.account_id=t.account_id
                    JOIN business_subscriptions subscription
                      ON subscription.tenant_id=t.tenant_id
                     AND subscription.account_id=t.account_id
                    ORDER BY p.display_name, t.tenant_id
                    """
                )
            ).mappings()
            customers = []
            all_statuses: list[tuple[CustomerStatus, ...]] = []
            for row in rows:
                statuses = customer_statuses(
                    subscription_state=str(row["subscription_state"]),
                    payment_pending=bool(row["payment_pending"]),
                    try_on_status=str(row["try_on_status"]),
                )
                all_statuses.append(statuses)
                customer = dict(row)
                customer["statuses"] = statuses
                customer.pop("payment_pending", None)
                if normalized is None or normalized in statuses:
                    customers.append(customer)
        return {"summary": customer_counts(all_statuses), "customers": customers}
