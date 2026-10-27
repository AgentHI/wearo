from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .admin_organizations import ADMIN_ACTOR_ID
from .tryon_authorization import SubscriptionState

SubscriptionAction = Literal[
    "START_TRIAL", "ACTIVATE", "MARK_PAYMENT_DUE", "PAUSE", "CANCEL", "EXPIRE"
]


class AdminSubscriptionError(ValueError):
    pass


def subscription_state_after(
    current: SubscriptionState, action: SubscriptionAction
) -> SubscriptionState:
    targets: dict[SubscriptionAction, SubscriptionState] = {
        "START_TRIAL": "TRIAL",
        "ACTIVATE": "ACTIVE",
        "MARK_PAYMENT_DUE": "PAYMENT_DUE",
        "PAUSE": "PAUSED",
        "CANCEL": "CANCELLED",
        "EXPIRE": "EXPIRED",
    }
    allowed: dict[SubscriptionState, frozenset[SubscriptionAction]] = {
        "TRIAL": frozenset({"ACTIVATE", "MARK_PAYMENT_DUE", "PAUSE", "CANCEL", "EXPIRE"}),
        "ACTIVE": frozenset({"MARK_PAYMENT_DUE", "PAUSE", "CANCEL", "EXPIRE"}),
        "PAYMENT_DUE": frozenset({"ACTIVATE", "PAUSE", "CANCEL", "EXPIRE"}),
        "PAUSED": frozenset({"ACTIVATE", "CANCEL", "EXPIRE"}),
        "CANCELLED": frozenset({"ACTIVATE", "START_TRIAL"}),
        "EXPIRED": frozenset({"ACTIVATE", "START_TRIAL"}),
    }
    if action not in allowed[current]:
        raise AdminSubscriptionError(f"Cannot {action.lower()} a {current.lower()} subscription.")
    return targets[action]


class PostgresAdminSubscriptions:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get(self, tenant_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT subscription_id, tenant_id, plan_code, state,
                              started_at, next_billing_at, trial_ends_at
                    FROM business_subscriptions WHERE tenant_id=:tenant"""
                    ),
                    {"tenant": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AdminSubscriptionError("Subscription not found.")
        return dict(row)

    def transition(
        self, tenant_id: UUID, action: SubscriptionAction, reason: str
    ) -> dict[str, object]:
        explanation = reason.strip()
        if not explanation:
            raise AdminSubscriptionError("A reason is required.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = self._locked(connection, tenant_id)
            before = str(row["state"])
            target = subscription_state_after(before, action)  # type: ignore[arg-type]
            trial_end = now + timedelta(days=14) if target == "TRIAL" else row["trial_ends_at"]
            next_billing = (
                now + timedelta(days=30) if target == "ACTIVE" else row["next_billing_at"]
            )
            if target == "ACTIVE":
                connection.execute(
                    text(
                        """INSERT INTO plan_assignments
                        (account_id, tenant_id, plan_code, effective_from, effective_until)
                        SELECT :account, :tenant, :plan, :now, :next_billing
                        WHERE NOT EXISTS (
                          SELECT 1 FROM plan_assignments
                          WHERE account_id=:account AND tenant_id=:tenant
                            AND cancelled_at IS NULL AND effective_from <= :now
                            AND (effective_until IS NULL OR effective_until > :now)
                        )"""
                    ),
                    {
                        "account": row["account_id"],
                        "tenant": tenant_id,
                        "plan": row["plan_code"],
                        "now": now,
                        "next_billing": next_billing,
                    },
                )
            connection.execute(
                text(
                    """UPDATE business_subscriptions
                    SET state=:state, trial_ends_at=:trial_end,
                        next_billing_at=:next_billing, updated_at=:now
                    WHERE tenant_id=:tenant"""
                ),
                {
                    "state": target,
                    "trial_end": trial_end,
                    "next_billing": next_billing,
                    "now": now,
                    "tenant": tenant_id,
                },
            )
            self._audit(
                connection,
                row,
                f"ADMIN_SUBSCRIPTION_{action}",
                explanation,
                before,
                target,
                now,
            )
        return self.get(tenant_id)

    def assign_plan(
        self, tenant_id: UUID, plan_code: str, next_billing_at: datetime | None, reason: str
    ) -> dict[str, object]:
        plan = plan_code.strip().upper()
        explanation = reason.strip()
        if not plan or len(plan) > 40 or not explanation:
            raise AdminSubscriptionError("A valid plan and reason are required.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = self._locked(connection, tenant_id)
            connection.execute(
                text(
                    "UPDATE plan_assignments SET effective_until=:now, updated_at=:now "
                    "WHERE account_id=:account AND tenant_id=:tenant "
                    "AND effective_until IS NULL"
                ),
                {"now": now, "account": row["account_id"], "tenant": tenant_id},
            )
            connection.execute(
                text(
                    """INSERT INTO plan_assignments
                    (account_id, tenant_id, plan_code, effective_from, effective_until)
                    VALUES (:account, :tenant, :plan, :now, :next_billing)"""
                ),
                {
                    "account": row["account_id"],
                    "tenant": tenant_id,
                    "plan": plan,
                    "now": now,
                    "next_billing": next_billing_at,
                },
            )
            connection.execute(
                text(
                    "UPDATE business_subscriptions SET plan_code=:plan, next_billing_at=:next, "
                    "updated_at=:now WHERE tenant_id=:tenant"
                ),
                {"plan": plan, "next": next_billing_at, "now": now, "tenant": tenant_id},
            )
            self._audit(
                connection,
                row,
                "ADMIN_SUBSCRIPTION_PLAN_CHANGED",
                explanation,
                str(row["plan_code"]),
                plan,
                now,
            )
        return self.get(tenant_id)

    def extend_trial(self, tenant_id: UUID, days: int, reason: str) -> dict[str, object]:
        if not 1 <= days <= 365 or not reason.strip():
            raise AdminSubscriptionError("Trial extension days and reason are required.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = self._locked(connection, tenant_id)
            if row["state"] != "TRIAL":
                raise AdminSubscriptionError("Only a trial subscription can be extended.")
            current_end = row["trial_ends_at"] or now
            new_end = max(current_end, now) + timedelta(days=days)
            connection.execute(
                text(
                    "UPDATE business_subscriptions SET trial_ends_at=:end, updated_at=:now "
                    "WHERE tenant_id=:tenant"
                ),
                {"end": new_end, "now": now, "tenant": tenant_id},
            )
            connection.execute(
                text(
                    "UPDATE plan_assignments SET effective_until=:end, updated_at=:now "
                    "WHERE account_id=:account AND tenant_id=:tenant AND plan_code=:plan "
                    "AND effective_from <= :now AND cancelled_at IS NULL"
                ),
                {
                    "end": new_end,
                    "now": now,
                    "account": row["account_id"],
                    "tenant": tenant_id,
                    "plan": row["plan_code"],
                },
            )
            self._audit(
                connection,
                row,
                "ADMIN_SUBSCRIPTION_TRIAL_EXTENDED",
                reason.strip(),
                str(current_end),
                str(new_end),
                now,
            )
        return self.get(tenant_id)

    @staticmethod
    def _locked(connection: Connection, tenant_id: UUID) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text("SELECT * FROM business_subscriptions WHERE tenant_id=:tenant FOR UPDATE"),
                {"tenant": tenant_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise AdminSubscriptionError("Subscription not found.")
        return dict(row)

    @staticmethod
    def _audit(
        connection: Connection,
        row: Mapping[str, Any],
        action: str,
        reason: str,
        before: str,
        after: str,
        now: datetime,
    ) -> None:
        connection.execute(
            text(
                """INSERT INTO audit_events
                (audit_event_id, account_id, tenant_id, actor_type, actor_id, action,
                 target_type, target_id, reason, before_summary, after_summary, occurred_at)
                VALUES (:event, :account, :tenant, 'ADMIN', :actor, :action,
                        'BUSINESS_SUBSCRIPTION', :subscription, :reason,
                        CAST(:before AS jsonb), CAST(:after AS jsonb), :now)"""
            ),
            {
                "event": uuid4(),
                "account": row["account_id"],
                "tenant": row["tenant_id"],
                "actor": ADMIN_ACTOR_ID,
                "action": action,
                "subscription": row["subscription_id"],
                "reason": reason,
                "before": json.dumps({"value": before}),
                "after": json.dumps({"value": after}),
                "now": now,
            },
        )
