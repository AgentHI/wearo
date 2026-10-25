from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .email_otp import normalize_destination
from .tenant_scope import TenantScopeError, require_tenant_scope


class BusinessAgentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_agent(name: str, mobile: str) -> tuple[str, str]:
    clean_name = name.strip()
    normalized_mobile = normalize_destination(mobile)
    if not clean_name or len(clean_name) > 120:
        raise BusinessAgentError("INVALID_AGENT_NAME", "Enter a valid agent name.")
    if not normalized_mobile or "@" in normalized_mobile:
        raise BusinessAgentError(
            "INVALID_AGENT_MOBILE", "Enter a mobile number with its country code."
        )
    return clean_name, normalized_mobile


class PostgresBusinessAgents:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise BusinessAgentError("AGENT_UNAVAILABLE", "Resource unavailable.") from None

    def list(self, principal_id: UUID, tenant_id: UUID) -> tuple[dict[str, object], ...]:
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            rows = connection.execute(
                text(
                    """SELECT agent_id, name, normalized_mobile, status, created_at, updated_at
                    FROM business_agents WHERE tenant_id=:tenant AND account_id=:account
                      AND status <> 'DELETED' ORDER BY name, agent_id"""
                ),
                {"tenant": tenant_id, "account": account_id},
            ).mappings()
            return tuple(dict(row) for row in rows)

    def save(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        agent_id: UUID | None,
        name: str,
        mobile: str,
    ) -> dict[str, object]:
        clean_name, normalized_mobile = validate_agent(name, mobile)
        now = datetime.now(UTC)
        actor_principal_id = principal_id
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            conflicting_business_identity = connection.execute(
                text(
                    """SELECT identity.principal_id
                    FROM principal_identities identity
                    JOIN principals principal
                      ON principal.principal_id=identity.principal_id
                     AND principal.account_id=identity.account_id
                    WHERE identity.channel='PHONE'
                      AND identity.normalized_value=:mobile
                      AND principal.principal_type='BUSINESS'
                      AND (CAST(:agent_principal AS uuid) IS NULL
                           OR identity.principal_id <> CAST(:agent_principal AS uuid))
                    LIMIT 1"""
                ),
                {
                    "mobile": normalized_mobile,
                    "agent_principal": (
                        connection.execute(
                            text("SELECT principal_id FROM business_agents WHERE agent_id=:agent"),
                            {"agent": agent_id},
                        ).scalar_one_or_none()
                        if agent_id
                        else None
                    ),
                },
            ).scalar_one_or_none()
            if conflicting_business_identity is not None:
                raise BusinessAgentError(
                    "AGENT_MOBILE_IN_USE",
                    "This mobile number already has business access. Use another number.",
                )
            identifier = agent_id or uuid4()
            if agent_id:
                row = (
                    connection.execute(
                        text(
                            """UPDATE business_agents SET name=:name, normalized_mobile=:mobile,
                               status='ACTIVE', updated_at=:now
                        WHERE agent_id=:agent AND tenant_id=:tenant AND account_id=:account
                          AND status <> 'DELETED'
                        RETURNING agent_id, name, normalized_mobile, status,
                                  created_at, updated_at"""
                        ),
                        {
                            "name": clean_name,
                            "mobile": normalized_mobile,
                            "now": now,
                            "agent": agent_id,
                            "tenant": tenant_id,
                            "account": account_id,
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                action = "BUSINESS_AGENT_UPDATED"
                if row is not None:
                    agent_principal_id = connection.execute(
                        text("SELECT principal_id FROM business_agents WHERE agent_id=:agent"),
                        {"agent": agent_id},
                    ).scalar_one_or_none()
                    if agent_principal_id is None:
                        agent_principal_id = uuid4()
                        connection.execute(
                            text("""INSERT INTO principals
                                (principal_id, account_id, account_kind, principal_type, status)
                                VALUES (:principal, :account, 'TENANT', 'BUSINESS', 'ACTIVE')"""),
                            {"principal": agent_principal_id, "account": account_id},
                        )
                        connection.execute(
                            text("""INSERT INTO principal_identities
                                (account_id, principal_id, channel, normalized_value)
                                VALUES (:account, :principal, 'PHONE', :mobile)"""),
                            {
                                "account": account_id,
                                "principal": agent_principal_id,
                                "mobile": normalized_mobile,
                            },
                        )
                        connection.execute(
                            text("""INSERT INTO tenant_memberships
                                (tenant_id, account_id, principal_id, role)
                                VALUES (:tenant, :account, :principal, 'ASSOCIATE')"""),
                            {
                                "tenant": tenant_id,
                                "account": account_id,
                                "principal": agent_principal_id,
                            },
                        )
                        connection.execute(
                            text(
                                """UPDATE business_agents SET principal_id=:principal
                                WHERE agent_id=:agent"""
                            ),
                            {"principal": agent_principal_id, "agent": agent_id},
                        )
                    else:
                        connection.execute(
                            text(
                                """UPDATE principal_identities SET normalized_value=:mobile,
                                updated_at=:now WHERE principal_id=:principal
                                  AND channel='PHONE'"""
                            ),
                            {
                                "mobile": normalized_mobile,
                                "now": now,
                                "principal": agent_principal_id,
                            },
                        )
            else:
                agent_principal_id = uuid4()
                connection.execute(
                    text("""INSERT INTO principals
                        (principal_id, account_id, account_kind, principal_type, status)
                        VALUES (:principal, :account, 'TENANT', 'BUSINESS', 'ACTIVE')"""),
                    {"principal": agent_principal_id, "account": account_id},
                )
                connection.execute(
                    text("""INSERT INTO principal_identities
                        (account_id, principal_id, channel, normalized_value)
                        VALUES (:account, :principal, 'PHONE', :mobile)"""),
                    {
                        "account": account_id,
                        "principal": agent_principal_id,
                        "mobile": normalized_mobile,
                    },
                )
                connection.execute(
                    text("""INSERT INTO tenant_memberships
                        (tenant_id, account_id, principal_id, role)
                        VALUES (:tenant, :account, :principal, 'ASSOCIATE')"""),
                    {"tenant": tenant_id, "account": account_id, "principal": agent_principal_id},
                )
                row = (
                    connection.execute(
                        text(
                            """INSERT INTO business_agents
                        (agent_id, tenant_id, account_id, principal_id, name,
                         normalized_mobile, status)
                        VALUES (:agent, :tenant, :account, :principal, :name, :mobile, 'ACTIVE')
                        RETURNING agent_id, name, normalized_mobile, status,
                                  created_at, updated_at"""
                        ),
                        {
                            "agent": identifier,
                            "tenant": tenant_id,
                            "account": account_id,
                            "principal": agent_principal_id,
                            "name": clean_name,
                            "mobile": normalized_mobile,
                        },
                    )
                    .mappings()
                    .one()
                )
                action = "BUSINESS_AGENT_CREATED"
            if row is None:
                raise BusinessAgentError("AGENT_UNAVAILABLE", "Resource unavailable.")
            self._audit(
                connection, account_id, tenant_id, actor_principal_id, identifier, action, now
            )
            return dict(row)

    def delete(self, principal_id: UUID, tenant_id: UUID, agent_id: UUID) -> None:
        now = datetime.now(UTC)
        actor_principal_id = principal_id
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            changed = connection.execute(
                text(
                    """UPDATE business_agents SET status='DELETED', updated_at=:now
                    WHERE agent_id=:agent AND tenant_id=:tenant AND account_id=:account
                      AND status <> 'DELETED'"""
                ),
                {"now": now, "agent": agent_id, "tenant": tenant_id, "account": account_id},
            ).rowcount
            if not changed:
                raise BusinessAgentError("AGENT_UNAVAILABLE", "Resource unavailable.")
            agent_principal_id = connection.execute(
                text("SELECT principal_id FROM business_agents WHERE agent_id=:agent"),
                {"agent": agent_id},
            ).scalar_one_or_none()
            if agent_principal_id is not None:
                connection.execute(
                    text(
                        """UPDATE tenant_memberships SET revoked_at=:now, updated_at=:now
                        WHERE tenant_id=:tenant AND principal_id=:principal
                          AND revoked_at IS NULL"""
                    ),
                    {"now": now, "tenant": tenant_id, "principal": agent_principal_id},
                )
                connection.execute(
                    text(
                        """UPDATE principals SET status='CLOSED', updated_at=:now
                        WHERE principal_id=:principal"""
                    ),
                    {"now": now, "principal": agent_principal_id},
                )
            self._audit(
                connection,
                account_id,
                tenant_id,
                actor_principal_id,
                agent_id,
                "BUSINESS_AGENT_DELETED",
                now,
            )

    def context(
        self,
        principal_id: UUID,
        origin: str,
        business_reference: str | None = None,
        public_key: str | None = None,
    ) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""SELECT a.agent_id, a.name, a.tenant_id, a.account_id,
                              p.display_name, p.logo_asset_id, t.slug, l.public_code,
                              t.try_on_status
                       FROM business_agents a
                       JOIN tenant_memberships m ON m.tenant_id=a.tenant_id
                         AND m.principal_id=a.principal_id AND m.revoked_at IS NULL
                       JOIN business_profiles p ON p.tenant_id=a.tenant_id
                         AND p.account_id=a.account_id
                       JOIN business_tenants t ON t.tenant_id=a.tenant_id
                         AND t.account_id=a.account_id
                       JOIN business_shop_links l ON l.tenant_id=a.tenant_id
                         AND l.account_id=a.account_id
                       WHERE a.principal_id=:principal AND a.status='ACTIVE'
                         AND t.status='ACTIVE' AND l.enabled
                         AND (CAST(:reference AS text) IS NULL OR
                              ((t.slug=:reference OR CAST(a.tenant_id AS text)=:reference)
                               AND l.public_code=:public_key))"""),
                    {
                        "principal": principal_id,
                        "reference": business_reference,
                        "public_key": public_key,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise BusinessAgentError("AGENT_UNAVAILABLE", "Agent access is unavailable.")
        result = dict(row)
        result["shop_url"] = f"{origin.rstrip('/')}/shop/{row['slug']}?key={row['public_code']}"
        result["agent_url"] = f"{origin.rstrip('/')}/agent/{row['slug']}?key={row['public_code']}"
        return result

    @staticmethod
    def _audit(
        connection: Connection,
        account_id: UUID,
        tenant_id: UUID,
        principal_id: UUID,
        agent_id: UUID,
        action: str,
        now: datetime,
    ) -> None:
        connection.execute(
            text(
                """INSERT INTO audit_events
                (account_id, tenant_id, actor_type, actor_id, action, target_type,
                 target_id, reason, occurred_at)
                VALUES (:account, :tenant, 'PRINCIPAL', :actor, :action,
                        'BUSINESS_AGENT', :agent, :reason, :now)"""
            ),
            {
                "account": account_id,
                "tenant": tenant_id,
                "actor": principal_id,
                "action": action,
                "agent": agent_id,
                "reason": action.replace("_", " ").title(),
                "now": now,
            },
        )
