from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope

SupportScope = Literal["CASE_METADATA", "BILLING", "RENDER_METADATA", "PRIVATE_MEDIA"]


class SupportAccessError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def required_admin_scope(scope: SupportScope) -> str:
    return f"support:{scope.casefold()}"


class PostgresSupportAccess:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def grant(
        self,
        *,
        admin_id: UUID,
        account_id: UUID,
        tenant_id: UUID | None,
        case_id: UUID,
        scope: SupportScope,
        reason: str,
        duration: timedelta = timedelta(hours=1),
    ) -> dict[str, object]:
        explanation = reason.strip()
        if not explanation or not timedelta(minutes=5) <= duration <= timedelta(hours=24):
            raise SupportAccessError(
                "INVALID_SUPPORT_GRANT", "Grant reason or duration is invalid."
            )
        now, grant_id = datetime.now(UTC), uuid4()
        with self.engine.begin() as connection:
            scopes = connection.execute(
                text(
                    "SELECT scopes FROM admin_identities WHERE admin_id=:admin AND status='ACTIVE'"
                ),
                {"admin": admin_id},
            ).scalar_one_or_none()
            if scopes is None or required_admin_scope(scope) not in scopes:
                raise SupportAccessError("SUPPORT_ACCESS_DENIED", "Support access denied.")
            case_exists = connection.execute(
                text("""SELECT case_id FROM operation_cases
                WHERE case_id=:case AND account_id=:account
                  AND tenant_id IS NOT DISTINCT FROM :tenant"""),
                {"case": case_id, "account": account_id, "tenant": tenant_id},
            ).scalar_one_or_none()
            if case_exists is None:
                raise SupportAccessError("CASE_UNAVAILABLE", "Case unavailable.")
            expires = now + duration
            row = (
                connection.execute(
                    text("""INSERT INTO support_access_grants
                (grant_id, account_id, tenant_id, case_id, admin_id, scope,
                 reason, expires_at)
                VALUES (:grant, :account, :tenant, :case, :admin, :scope,
                        :reason, :expires)
                RETURNING grant_id, case_id, admin_id, scope, reason, expires_at, revoked_at"""),
                    {
                        "grant": grant_id,
                        "account": account_id,
                        "tenant": tenant_id,
                        "case": case_id,
                        "admin": admin_id,
                        "scope": scope,
                        "reason": explanation,
                        "expires": expires,
                    },
                )
                .mappings()
                .one()
            )
            self._audit(
                connection,
                account_id,
                tenant_id,
                admin_id,
                "SUPPORT_ACCESS_GRANTED",
                grant_id,
                explanation,
                now,
            )
            return dict(row)

    def authorize(self, admin_id: UUID, grant_id: UUID, scope: SupportScope) -> dict[str, object]:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            grant = (
                connection.execute(
                    text("""SELECT g.*, a.scopes, a.status AS admin_status
                FROM support_access_grants g JOIN admin_identities a ON a.admin_id=g.admin_id
                WHERE g.grant_id=:grant AND g.admin_id=:admin FOR UPDATE"""),
                    {"grant": grant_id, "admin": admin_id},
                )
                .mappings()
                .one_or_none()
            )
            if (
                grant is None
                or grant["scope"] != scope
                or grant["revoked_at"] is not None
                or grant["expires_at"] <= now
                or grant["admin_status"] != "ACTIVE"
                or required_admin_scope(scope) not in grant["scopes"]
            ):
                raise SupportAccessError("SUPPORT_ACCESS_DENIED", "Support access denied.")
            self._audit(
                connection,
                grant["account_id"],
                grant["tenant_id"],
                admin_id,
                "SUPPORT_DATA_ACCESSED",
                grant_id,
                f"Case-bound minimum-data access for {scope}.",
                now,
            )
            return self._minimum_data(
                connection, grant["account_id"], grant["tenant_id"], grant["case_id"], scope
            )

    def list_for_owner(self, principal_id: UUID, tenant_id: UUID) -> tuple[dict[str, object], ...]:
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            rows = connection.execute(
                text("""SELECT grant_id, case_id, admin_id, scope, reason,
                       expires_at, revoked_at, created_at
                FROM support_access_grants WHERE account_id=:account AND tenant_id=:tenant
                ORDER BY created_at DESC"""),
                {"account": account_id, "tenant": tenant_id},
            ).mappings()
            return tuple(dict(row) for row in rows)

    def revoke(self, principal_id: UUID, tenant_id: UUID, grant_id: UUID) -> None:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            grant = connection.execute(
                text("""UPDATE support_access_grants
                SET revoked_at=:now, updated_at=:now
                WHERE grant_id=:grant AND account_id=:account AND tenant_id=:tenant
                  AND revoked_at IS NULL
                RETURNING admin_id"""),
                {"now": now, "grant": grant_id, "account": account_id, "tenant": tenant_id},
            ).scalar_one_or_none()
            if grant is None:
                raise SupportAccessError("SUPPORT_GRANT_UNAVAILABLE", "Resource unavailable.")
            self._audit(
                connection,
                account_id,
                tenant_id,
                principal_id,
                "SUPPORT_ACCESS_REVOKED",
                grant_id,
                "Tenant owner revoked access.",
                now,
                actor_type="PRINCIPAL",
            )

    @staticmethod
    def _owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise SupportAccessError("SUPPORT_GRANT_UNAVAILABLE", "Resource unavailable.") from None

    @staticmethod
    def _minimum_data(
        connection: Connection, account: UUID, tenant: UUID | None, case: UUID, scope: SupportScope
    ) -> dict[str, object]:
        if scope == "CASE_METADATA":
            row = (
                connection.execute(
                    text("""SELECT case_id, case_type, state, reason,
                       disposition, created_at, resolved_at FROM operation_cases
                WHERE case_id=:case AND account_id=:account"""),
                    {"case": case, "account": account},
                )
                .mappings()
                .one()
            )
            return dict(row)
        if scope == "BILLING":
            rows = connection.execute(
                text("""SELECT payment_order_id, state, amount_minor,
                       currency, created_at FROM payment_orders
                WHERE account_id=:account AND tenant_id IS NOT DISTINCT FROM :tenant
                ORDER BY created_at DESC LIMIT 50"""),
                {"account": account, "tenant": tenant},
            ).mappings()
            return {"payments": tuple(dict(row) for row in rows)}
        if scope == "RENDER_METADATA":
            rows = connection.execute(
                text("""SELECT job_id, status, error_code, created_at
                FROM render_jobs WHERE account_id=:account
                  AND tenant_id IS NOT DISTINCT FROM :tenant
                ORDER BY created_at DESC LIMIT 50"""),
                {"account": account, "tenant": tenant},
            ).mappings()
            return {"renders": tuple(dict(row) for row in rows)}
        rows = connection.execute(
            text("""SELECT asset_id, mime_type, purpose, validation_state,
                   retention_state, deletion_state, created_at FROM media_assets
            WHERE account_id=:account ORDER BY created_at DESC LIMIT 20"""),
            {"account": account},
        ).mappings()
        return {"media_metadata": tuple(dict(row) for row in rows), "content_included": False}

    @staticmethod
    def _audit(
        connection: Connection,
        account: UUID,
        tenant: UUID | None,
        actor: UUID,
        action: str,
        target: UUID,
        reason: str,
        now: datetime,
        actor_type: str = "ADMIN",
    ) -> None:
        connection.execute(
            text("""INSERT INTO audit_events
            (account_id, tenant_id, actor_type, actor_id, action, target_type,
             target_id, reason, occurred_at)
            VALUES (:account, :tenant, :actor_type, :actor, :action,
                    'SUPPORT_ACCESS_GRANT', :target, :reason, :now)"""),
            {
                "account": account,
                "tenant": tenant,
                "actor_type": actor_type,
                "actor": actor,
                "action": action,
                "target": target,
                "reason": reason,
                "now": now,
            },
        )
