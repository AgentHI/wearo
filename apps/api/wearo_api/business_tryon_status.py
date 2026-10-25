from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope
from .tryon_authorization import BusinessTryOnStatus


class BusinessTryOnStatusError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PostgresBusinessTryOnStatus:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            try:
                scope = require_tenant_scope(
                    connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
                )
            except TenantScopeError:
                raise BusinessTryOnStatusError(
                    "TRY_ON_STATUS_UNAVAILABLE", "Try-on status is unavailable."
                ) from None
            status = cast(
                BusinessTryOnStatus,
                connection.execute(
                    text(
                        "SELECT try_on_status FROM business_tenants "
                        "WHERE tenant_id=:tenant AND account_id=:account"
                    ),
                    {"tenant": tenant_id, "account": scope.account_id},
                ).scalar_one(),
            )
        return {"status": status}

    def transition(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        target: BusinessTryOnStatus,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current_time = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            try:
                scope = require_tenant_scope(
                    connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
                )
            except TenantScopeError:
                raise BusinessTryOnStatusError(
                    "TRY_ON_STATUS_UNAVAILABLE", "Try-on status is unavailable."
                ) from None
            current = cast(
                BusinessTryOnStatus,
                connection.execute(
                    text(
                        "SELECT try_on_status FROM business_tenants "
                        "WHERE tenant_id=:tenant AND account_id=:account FOR UPDATE"
                    ),
                    {"tenant": tenant_id, "account": scope.account_id},
                ).scalar_one(),
            )
            allowed = {
                "ACTIVE": frozenset({"PAUSED", "CANCELLED"}),
                "PAUSED": frozenset({"ACTIVE", "CANCELLED"}),
                "CANCELLED": frozenset(),
            }
            if target == current:
                return {"status": current}
            if target not in allowed[current]:
                raise BusinessTryOnStatusError(
                    "TRY_ON_STATUS_CONFLICT",
                    "A cancelled subscription cannot be resumed or paused.",
                )
            connection.execute(
                text(
                    "UPDATE business_tenants SET try_on_status=:status, updated_at=:now "
                    "WHERE tenant_id=:tenant AND account_id=:account"
                ),
                {
                    "status": target,
                    "now": current_time,
                    "tenant": tenant_id,
                    "account": scope.account_id,
                },
            )
            if target == "CANCELLED":
                connection.execute(
                    text(
                        "UPDATE plan_assignments SET cancelled_at=COALESCE(cancelled_at, :now), "
                        "updated_at=:now WHERE account_id=:account AND tenant_id=:tenant "
                        "AND effective_from <= :now "
                        "AND (effective_until IS NULL OR effective_until > :now)"
                    ),
                    {"now": current_time, "account": scope.account_id, "tenant": tenant_id},
                )
            connection.execute(
                text(
                    "INSERT INTO audit_events "
                    "(audit_event_id, account_id, tenant_id, actor_type, actor_id, action, "
                    "target_type, target_id, reason, before_summary, after_summary, occurred_at) "
                    "VALUES (:event, :account, :tenant, 'PRINCIPAL', :actor, :action, "
                    "'BUSINESS_TENANT', :tenant, :reason, CAST(:before AS jsonb), "
                    "CAST(:after AS jsonb), :now)"
                ),
                {
                    "event": uuid4(),
                    "account": scope.account_id,
                    "tenant": tenant_id,
                    "actor": principal_id,
                    "action": f"BUSINESS_TRY_ON_{target}",
                    "reason": "Business owner changed try-on availability.",
                    "before": json.dumps({"status": current}),
                    "after": json.dumps({"status": target}),
                    "now": current_time,
                },
            )
        return {"status": target}
