from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from .email_otp import normalize_destination
from .tenant_scope import TenantScopeError, require_tenant_scope

AllowanceAction = Literal["RESET", "ADD"]


class BusinessAllowanceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_mobile(value: str) -> str:
    mobile = normalize_destination(value)
    if not mobile or "@" in mobile:
        raise BusinessAllowanceError("INVALID_MOBILE", "Enter an international mobile number.")
    return mobile


class PostgresBusinessAllowances:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise BusinessAllowanceError("ALLOWANCE_UNAVAILABLE", "Resource unavailable.") from None

    @staticmethod
    def _agent(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            scope = require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"ASSOCIATE"})
            )
        except TenantScopeError:
            raise BusinessAllowanceError("ALLOWANCE_UNAVAILABLE", "Resource unavailable.") from None
        active: bool = bool(
            connection.execute(
                text("""SELECT EXISTS (SELECT 1 FROM business_agents
                WHERE tenant_id=:tenant AND principal_id=:principal AND status='ACTIVE')"""),
                {"tenant": tenant_id, "principal": principal_id},
            ).scalar_one()
        )
        if not active:
            raise BusinessAllowanceError("ALLOWANCE_UNAVAILABLE", "Resource unavailable.")
        return scope.account_id

    def get(
        self, principal_id: UUID, tenant_id: UUID, mobile: str | None = None, *, agent: bool = False
    ) -> dict[str, object]:
        with self.engine.connect() as connection:
            account_id = (self._agent if agent else self._owner)(
                connection, principal_id, tenant_id
            )
            policy = dict(
                connection.execute(
                    text(
                        """SELECT default_try_on_limit, period, updated_at
                        FROM business_allowance_policies
                        WHERE tenant_id=:tenant AND account_id=:account"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one()
            )
            user = None
            if mobile:
                normalized = normalize_mobile(mobile)
                legacy_mobile = (
                    normalized[3:]
                    if normalized.startswith("+91") and len(normalized) == 13
                    else normalized
                )
                row = (
                    connection.execute(
                        text(
                            """SELECT normalized_mobile, limit_adjustment, used_count,
                                      period_started_at
                            FROM business_user_allowances
                            WHERE tenant_id=:tenant AND account_id=:account
                              AND normalized_mobile=:mobile"""
                        ),
                        {"tenant": tenant_id, "account": account_id, "mobile": normalized},
                    )
                    .mappings()
                    .one_or_none()
                )
                adjustment = int(row["limit_adjustment"]) if row else 0
                allowance_used = int(row["used_count"]) if row else 0
                consumer_used = int(
                    connection.execute(
                        text(
                            """SELECT COALESCE(SUM(usage.successful_generations), 0)
                            FROM principal_identities identity
                            JOIN principals principal
                              ON principal.principal_id=identity.principal_id
                             AND principal.account_id=identity.account_id
                            JOIN generation_daily_usage usage
                              ON usage.account_id=identity.account_id
                            WHERE identity.channel='PHONE'
                              AND identity.normalized_value IN (:mobile, :legacy_mobile)
                              AND principal.principal_type='CONSUMER'
                              AND usage.usage_date_ist =
                                  (now() AT TIME ZONE 'Asia/Kolkata')::date"""
                        ),
                        {"mobile": normalized, "legacy_mobile": legacy_mobile},
                    ).scalar_one()
                )
                used = max(allowance_used, consumer_used)
                user = {
                    "normalized_mobile": normalized,
                    "limit_adjustment": adjustment,
                    "used_count": used,
                    "effective_limit": int(policy["default_try_on_limit"]) + adjustment,
                    "remaining": max(int(policy["default_try_on_limit"]) + adjustment - used, 0),
                }
            return {"policy": policy, "user": user}

    def update_policy(self, principal_id: UUID, tenant_id: UUID, limit: int) -> dict[str, object]:
        if not 0 <= limit <= 100000:
            raise BusinessAllowanceError("INVALID_ALLOWANCE", "Allowance is out of range.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            row = (
                connection.execute(
                    text(
                        """UPDATE business_allowance_policies
                SET default_try_on_limit=:limit, period=:period,
                    updated_by_principal_id=:actor, updated_at=:now
                WHERE tenant_id=:tenant AND account_id=:account
                RETURNING default_try_on_limit, period, updated_at"""
                    ),
                    {
                        "limit": limit,
                        "period": "DAY",
                        "actor": principal_id,
                        "now": now,
                        "tenant": tenant_id,
                        "account": account_id,
                    },
                )
                .mappings()
                .one()
            )
            self._audit(
                connection,
                account_id,
                tenant_id,
                principal_id,
                "BUSINESS_ALLOWANCE_UPDATED",
                "Business allowance policy updated.",
                now,
            )
            return dict(row)

    def find_participant(
        self, principal_id: UUID, tenant_id: UUID, mobile: str
    ) -> dict[str, object]:
        normalized = normalize_mobile(mobile)
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            found: bool = bool(
                connection.execute(
                    text(
                        """SELECT EXISTS (
                        SELECT 1 FROM business_participants
                        WHERE tenant_id=:tenant AND business_account_id=:account
                          AND normalized_mobile=:mobile
                        )"""
                    ),
                    {"tenant": tenant_id, "account": account_id, "mobile": normalized},
                ).scalar_one()
            )
        return {"found": found}

    def list_participants(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, object]:
        if page < 1 or not 1 <= page_size <= 50:
            raise BusinessAllowanceError("INVALID_PAGE", "Invalid customer page requested.")
        search_digits = "".join(character for character in (search or "") if character.isdigit())
        search_pattern = f"%{search_digits}%" if search_digits else None
        offset = (page - 1) * page_size
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            parameters = {
                "tenant": tenant_id,
                "account": account_id,
                "search": search_pattern,
                "limit": page_size,
                "offset": offset,
            }
            total = int(
                connection.execute(
                    text(
                        """SELECT count(*) FROM business_participants
                        WHERE tenant_id=:tenant AND business_account_id=:account
                          AND (CAST(:search AS text) IS NULL
                               OR regexp_replace(normalized_mobile, '[^0-9]', '', 'g')
                                  LIKE :search)"""
                    ),
                    parameters,
                ).scalar_one()
            )
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT p.participant_id, p.normalized_mobile, p.first_seen_at,
                               p.latest_seen_at,
                               count(*) FILTER (WHERE job.status='DELIVERED') AS try_on_count,
                               max(job.updated_at) FILTER (WHERE job.status='DELIVERED')
                                 AS latest_try_on_at
                        FROM business_participants p
                        LEFT JOIN business_sponsored_sessions session
                          ON session.participant_id=p.participant_id
                        LEFT JOIN business_sponsored_tryons sponsored
                          ON sponsored.session_id=session.session_id
                        LEFT JOIN render_jobs job
                          ON job.idempotency_key=substring(sponsored.request_key FROM 11)
                        WHERE p.tenant_id=:tenant AND p.business_account_id=:account
                          AND (CAST(:search AS text) IS NULL
                               OR regexp_replace(p.normalized_mobile, '[^0-9]', '', 'g')
                                  LIKE :search)
                        GROUP BY p.participant_id
                        ORDER BY latest_try_on_at DESC NULLS LAST,
                                 p.latest_seen_at DESC, p.participant_id DESC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    parameters,
                )
                .mappings()
                .all()
            )
        return {
            "items": [
                {
                    "participant_id": row["participant_id"],
                    "mobile": row["normalized_mobile"],
                    "try_on_count": int(row["try_on_count"]),
                    "latest_try_on_at": row["latest_try_on_at"],
                    "first_seen_at": row["first_seen_at"],
                    "latest_seen_at": row["latest_seen_at"],
                }
                for row in rows
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_previous": page > 1,
            "has_next": offset + len(rows) < total,
        }

    def adjust_user(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        mobile: str,
        action: AllowanceAction,
        amount: int = 0,
        *,
        agent: bool = False,
    ) -> dict[str, object]:
        normalized = normalize_mobile(mobile)
        if action == "ADD" and not 1 <= amount <= 100000:
            raise BusinessAllowanceError("INVALID_ALLOWANCE", "Added allowance is out of range.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            account_id = (self._agent if agent else self._owner)(
                connection, principal_id, tenant_id
            )
            connection.execute(
                text("""INSERT INTO business_user_allowances
                (tenant_id, account_id, normalized_mobile, limit_adjustment, used_count,
                 period_started_at, updated_by_principal_id)
                VALUES (:tenant, :account, :mobile, :amount, 0, :now, :actor)
                ON CONFLICT (tenant_id, normalized_mobile) DO UPDATE SET
                  limit_adjustment = CASE WHEN :action='RESET' THEN 0
                    ELSE business_user_allowances.limit_adjustment + :amount END,
                  used_count = CASE WHEN :action='RESET' THEN 0
                    ELSE business_user_allowances.used_count END,
                  period_started_at = CASE WHEN :action='RESET' THEN :now
                    ELSE business_user_allowances.period_started_at END,
                  updated_by_principal_id=:actor, updated_at=:now
                RETURNING normalized_mobile, limit_adjustment, used_count, period_started_at"""),
                {
                    "tenant": tenant_id,
                    "account": account_id,
                    "mobile": normalized,
                    "amount": amount if action == "ADD" else 0,
                    "action": action,
                    "now": now,
                    "actor": principal_id,
                },
            )
            if action == "ADD":
                connection.execute(
                    text(
                        """UPDATE business_sponsored_sessions session
                        SET allowance_limit=session.allowance_limit + :amount,
                            status=CASE WHEN session.status='EXHAUSTED'
                              THEN 'ACTIVE' ELSE session.status END,
                            updated_at=:now
                        FROM business_participants participant
                        WHERE session.participant_id=participant.participant_id
                          AND session.tenant_id=:tenant
                          AND session.business_account_id=:account
                          AND participant.normalized_mobile=:mobile
                          AND session.status IN ('ACTIVE', 'EXHAUSTED')
                          AND session.expires_at > :now"""
                    ),
                    {
                        "tenant": tenant_id,
                        "account": account_id,
                        "mobile": normalized,
                        "amount": amount,
                        "now": now,
                    },
                )
            self._audit(
                connection,
                account_id,
                tenant_id,
                principal_id,
                f"USER_ALLOWANCE_{action}",
                f"User allowance {action.casefold()}.",
                now,
            )
        return self.get(principal_id, tenant_id, normalized, agent=agent)

    @staticmethod
    def _audit(
        connection: Connection,
        account: UUID,
        tenant: UUID,
        actor: UUID,
        action: str,
        reason: str,
        now: datetime,
    ) -> None:
        connection.execute(
            text("""INSERT INTO audit_events
            (account_id, tenant_id, actor_type, actor_id, action, target_type, reason, occurred_at)
            VALUES (:account, :tenant, 'PRINCIPAL', :actor, :action,
                    'BUSINESS_ALLOWANCE', :reason, :now)"""),
            {
                "account": account,
                "tenant": tenant,
                "actor": actor,
                "action": action,
                "reason": reason,
                "now": now,
            },
        )
