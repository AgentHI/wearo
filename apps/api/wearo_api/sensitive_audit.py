from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope


class SensitiveAuditError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_audit_reason(reason: str) -> str:
    value = reason.strip()
    if not value or len(value) > 500:
        raise SensitiveAuditError("AUDIT_REASON_REQUIRED", "An audit reason is required.")
    return value


class PostgresSensitiveAudit:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def record(
        self,
        *,
        actor_id: UUID | None,
        action: str,
        target_id: UUID | None,
        occurred_at: datetime,
    ) -> None:
        """AdminAuth-compatible sink; authentication action is also its reason."""
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO audit_events
                    (audit_event_id, actor_type, actor_id, action, target_type,
                     target_id, reason, occurred_at)
                    VALUES (:event, :actor_type, :actor, :action, 'ADMIN_AUTH',
                            :target, :reason, :occurred)"""
                ),
                {
                    "event": uuid4(),
                    "actor_type": "ADMIN" if actor_id else "SYSTEM",
                    "actor": actor_id,
                    "action": action.upper().replace(".", "_")[:80],
                    "target": target_id,
                    "reason": action,
                    "occurred": occurred_at,
                },
            )

    def record_tenant_action(
        self,
        *,
        account_id: UUID,
        tenant_id: UUID,
        actor_id: UUID | None,
        actor_type: str,
        action: str,
        target_type: str,
        target_id: UUID | None,
        reason: str,
    ) -> None:
        explanation = validate_audit_reason(reason)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO audit_events
                    (audit_event_id, account_id, tenant_id, actor_type, actor_id,
                     action, target_type, target_id, reason, occurred_at)
                    VALUES (:event, :account, :tenant, :actor_type, :actor,
                            :action, :target_type, :target, :reason, :now)"""
                ),
                {
                    "event": uuid4(),
                    "account": account_id,
                    "tenant": tenant_id,
                    "actor_type": actor_type,
                    "actor": actor_id,
                    "action": action,
                    "target_type": target_type,
                    "target": target_id,
                    "reason": explanation,
                    "now": datetime.now(UTC),
                },
            )

    def list_for_tenant(
        self, principal_id: UUID, tenant_id: UUID, *, limit: int = 100
    ) -> dict[str, object]:
        size = max(1, min(limit, 250))
        with self.engine.connect() as connection:
            try:
                scope = require_tenant_scope(
                    connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
                )
            except TenantScopeError:
                raise SensitiveAuditError("AUDIT_UNAVAILABLE", "Resource unavailable.") from None
            rows = connection.execute(
                text(
                    """SELECT audit_event_id, actor_type, actor_id, action, target_type,
                              target_id, reason, occurred_at
                    FROM audit_events WHERE account_id=:account AND tenant_id=:tenant
                    ORDER BY occurred_at DESC, audit_event_id DESC LIMIT :limit"""
                ),
                {"account": scope.account_id, "tenant": tenant_id, "limit": size},
            ).mappings()
            return {"items": tuple(dict(row) for row in rows)}
