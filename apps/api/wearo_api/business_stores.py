from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from .email_otp import normalize_destination, normalize_email
from .plan_usage import BUSINESS_REPORTING_TIMEZONE
from .tenant_scope import TenantScopeError, require_tenant_scope


class BusinessStoreError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_store(name: str, code: str) -> tuple[str, str]:
    clean_name = name.strip()
    clean_code = re.sub(r"[^a-z0-9]+", "-", code.strip().casefold()).strip("-")
    if not clean_name or len(clean_name) > 120:
        raise BusinessStoreError("INVALID_STORE_NAME", "Enter a valid store name.")
    if not clean_code or len(clean_code) > 40:
        raise BusinessStoreError("INVALID_STORE_CODE", "Enter a valid store code.")
    return clean_name, clean_code


class PostgresBusinessStores:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise BusinessStoreError("STORE_UNAVAILABLE", "Resource unavailable.") from None

    def list(self, principal_id: UUID, tenant_id: UUID) -> tuple[dict[str, object], ...]:
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            rows = connection.execute(
                text("""SELECT s.store_id, s.name, s.code, s.status, s.admin_principal_id,
                    email.normalized_value admin_email, phone.normalized_value admin_mobile,
                    count(a.agent_id) FILTER (WHERE a.status <> 'DELETED') agent_count,
                    s.created_at, s.updated_at
                FROM business_stores s
                LEFT JOIN principal_identities email ON email.principal_id=s.admin_principal_id
                  AND email.channel='EMAIL'
                LEFT JOIN principal_identities phone ON phone.principal_id=s.admin_principal_id
                  AND phone.channel='PHONE'
                LEFT JOIN business_agents a ON a.store_id=s.store_id
                WHERE s.tenant_id=:tenant AND s.account_id=:account
                GROUP BY s.store_id, email.normalized_value, phone.normalized_value
                ORDER BY s.name, s.store_id"""),
                {"tenant": tenant_id, "account": account_id},
            ).mappings()
            return tuple(dict(row) for row in rows)

    def save(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        store_id: UUID | None,
        name: str,
        code: str,
        admin_email: str,
        admin_mobile: str,
    ) -> dict[str, object]:
        clean_name, clean_code = validate_store(name, code)
        email = normalize_email(admin_email)
        mobile = normalize_destination(admin_mobile)
        if not email:
            raise BusinessStoreError("INVALID_ADMIN_EMAIL", "Enter a valid admin email.")
        if not mobile or "@" in mobile:
            raise BusinessStoreError(
                "INVALID_ADMIN_MOBILE", "Enter an international mobile number."
            )
        now = datetime.now(UTC)
        try:
            with self.engine.begin() as connection:
                account_id = self._owner(connection, principal_id, tenant_id)
                existing = None
                if store_id:
                    existing = connection.execute(
                        text("""SELECT admin_principal_id FROM business_stores
                        WHERE store_id=:store AND tenant_id=:tenant AND account_id=:account"""),
                        {"store": store_id, "tenant": tenant_id, "account": account_id},
                    ).scalar_one_or_none()
                admin_id = existing or uuid4()
                if existing is None:
                    connection.execute(
                        text("""INSERT INTO principals
                        (principal_id, account_id, account_kind, principal_type, status)
                        VALUES (:principal, :account, 'TENANT', 'BUSINESS', 'ACTIVE')"""),
                        {"principal": admin_id, "account": account_id},
                    )
                    connection.execute(
                        text("""INSERT INTO tenant_memberships
                        (tenant_id, account_id, principal_id, role)
                        VALUES (:tenant, :account, :principal, 'ASSOCIATE')"""),
                        {"tenant": tenant_id, "account": account_id, "principal": admin_id},
                    )
                for channel, value in (("EMAIL", email), ("PHONE", mobile)):
                    connection.execute(
                        text("""INSERT INTO principal_identities
                        (account_id, principal_id, channel, normalized_value, verified_at)
                        VALUES (:account, :principal, :channel, :value, :now)
                        ON CONFLICT (principal_id, channel) DO UPDATE SET
                          normalized_value=EXCLUDED.normalized_value,
                          verified_at=EXCLUDED.verified_at, updated_at=:now"""),
                        {
                            "account": account_id,
                            "principal": admin_id,
                            "channel": channel,
                            "value": value,
                            "now": now,
                        },
                    )
                identifier = store_id or uuid4()
                if store_id:
                    row = (
                        connection.execute(
                            text("""UPDATE business_stores SET
                        name=:name, code=:code, admin_principal_id=:admin, updated_at=:now
                        WHERE store_id=:store AND tenant_id=:tenant AND account_id=:account
                        RETURNING store_id, name, code, status, admin_principal_id,
                                  created_at, updated_at"""),
                            {
                                "name": clean_name,
                                "code": clean_code,
                                "admin": admin_id,
                                "now": now,
                                "store": identifier,
                                "tenant": tenant_id,
                                "account": account_id,
                            },
                        )
                        .mappings()
                        .one_or_none()
                    )
                else:
                    row = (
                        connection.execute(
                            text("""INSERT INTO business_stores
                        (store_id, tenant_id, account_id, admin_principal_id, name, code)
                        VALUES (:store, :tenant, :account, :admin, :name, :code)
                        RETURNING store_id, name, code, status, admin_principal_id,
                                  created_at, updated_at"""),
                            {
                                "store": identifier,
                                "tenant": tenant_id,
                                "account": account_id,
                                "admin": admin_id,
                                "name": clean_name,
                                "code": clean_code,
                            },
                        )
                        .mappings()
                        .one()
                    )
                if row is None:
                    raise BusinessStoreError("STORE_UNAVAILABLE", "Resource unavailable.")
                return {**dict(row), "admin_email": email, "admin_mobile": mobile}
        except IntegrityError as error:
            raise BusinessStoreError(
                "STORE_DETAILS_IN_USE", "That store code, email, or mobile is already in use."
            ) from error

    def context(self, principal_id: UUID) -> dict[str, object]:
        today = datetime.now(BUSINESS_REPORTING_TIMEZONE).date()
        period_start = datetime.combine(today, time.min, BUSINESS_REPORTING_TIMEZONE).astimezone(
            UTC
        )
        period_end = period_start + timedelta(days=1)
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""SELECT s.store_id, s.tenant_id, s.account_id,
                    s.name, s.code, p.display_name business_name, t.advertisements_enabled
                FROM business_stores s JOIN business_profiles p
                  ON p.tenant_id=s.tenant_id AND p.account_id=s.account_id
                JOIN business_tenants t
                  ON t.tenant_id=s.tenant_id AND t.account_id=s.account_id
                WHERE s.admin_principal_id=:principal AND s.status='ACTIVE'"""),
                    {"principal": principal_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise BusinessStoreError("STORE_UNAVAILABLE", "Store access is unavailable.")
            counts = (
                connection.execute(
                    text("""SELECT
                    count(*) FILTER (WHERE status <> 'DELETED') agents,
                    count(*) FILTER (WHERE status = 'ACTIVE') active_agents
                FROM business_agents WHERE store_id=:store"""),
                    {"store": row["store_id"]},
                )
                .mappings()
                .one()
            )
            usage = (
                connection.execute(
                    text("""SELECT count(*) total_try_ons,
                    count(*) FILTER (WHERE j.status='DELIVERED') successful_try_ons,
                    COALESCE(sum((r.provider_usage->>'input_tokens')::bigint), 0)
                      provider_input_tokens,
                    COALESCE(sum((r.provider_usage->>'output_tokens')::bigint), 0)
                      provider_output_tokens,
                    COALESCE(sum(COALESCE((r.provider_usage->>'input_tokens')::bigint, 0)
                      + COALESCE((r.provider_usage->>'output_tokens')::bigint, 0)), 0)
                      provider_total_tokens,
                    COALESCE(sum(c.cost_usd_micros), 0) provider_cost_usd_micros
                FROM business_sponsored_tryons t
                JOIN business_sponsored_sessions ss ON ss.session_id=t.session_id
                  AND ss.tenant_id=t.tenant_id
                  AND ss.business_account_id=t.business_account_id
                LEFT JOIN render_jobs j ON j.job_id=t.render_job_id
                LEFT JOIN render_results r ON r.job_id=j.job_id
                LEFT JOIN model_usage_costs c ON c.job_id=j.job_id
                WHERE t.tenant_id=:tenant AND t.business_account_id=:account
                  AND ss.store_id=:store
                  AND j.created_at >= :period_start AND j.created_at < :period_end"""),
                    {
                        "tenant": row["tenant_id"],
                        "account": row["account_id"],
                        "store": row["store_id"],
                        "period_start": period_start,
                        "period_end": period_end,
                    },
                )
                .mappings()
                .one()
            )
        return {**dict(row), **dict(counts), **dict(usage), "usage_date": today}
