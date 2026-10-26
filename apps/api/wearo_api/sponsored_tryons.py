from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .tryon_authorization import BusinessTryOnStatus, authorize_business_try_on


class SponsoredTryOnError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PostgresSponsoredTryOns:
    session_ttl = timedelta(hours=24)

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _sync_session_allowance(
        connection: Connection, session_id: UUID, current: datetime
    ) -> None:
        connection.execute(
            text(
                """UPDATE business_sponsored_sessions session
                SET allowance_limit=GREATEST(
                      policy.default_try_on_limit + COALESCE(user_allowance.limit_adjustment, 0),
                      0
                    ),
                    status=CASE
                      WHEN session.expires_at <= :now THEN 'EXPIRED'
                      WHEN session.try_ons_used >= GREATEST(
                        policy.default_try_on_limit
                          + COALESCE(user_allowance.limit_adjustment, 0), 0
                      ) THEN 'EXHAUSTED'
                      ELSE 'ACTIVE'
                    END,
                    updated_at=:now
                FROM business_participants participant
                JOIN business_allowance_policies policy
                  ON policy.tenant_id=participant.tenant_id
                 AND policy.account_id=participant.business_account_id
                LEFT JOIN business_user_allowances user_allowance
                  ON user_allowance.tenant_id=participant.tenant_id
                 AND user_allowance.account_id=participant.business_account_id
                 AND user_allowance.normalized_mobile=participant.normalized_mobile
                WHERE session.session_id=:session
                  AND session.participant_id=participant.participant_id"""
            ),
            {"session": session_id, "now": current},
        )

    def activate(
        self,
        *,
        business_reference: str,
        public_key: str,
        consumer_account_id: UUID,
        consumer_principal_id: UUID,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = now or datetime.now(UTC)
        expires_at = current + self.session_ttl
        with self.engine.begin() as connection:
            context = (
                connection.execute(
                    text(
                        """SELECT l.tenant_id, l.account_id AS business_account_id,
                                  p.display_name, t.try_on_status
                        FROM business_shop_links l
                        JOIN business_tenants t
                          ON t.tenant_id=l.tenant_id AND t.account_id=l.account_id
                        JOIN business_profiles p
                          ON p.tenant_id=l.tenant_id AND p.account_id=l.account_id
                        WHERE (t.slug=:reference OR CAST(t.tenant_id AS text)=:reference)
                          AND (l.public_code=:key OR CAST(l.public_token AS text)=:key)
                          AND l.enabled AND t.status='ACTIVE'"""
                    ),
                    {"reference": business_reference, "key": public_key},
                )
                .mappings()
                .one_or_none()
            )
            if context is None:
                raise SponsoredTryOnError("SHOP_UNAVAILABLE", "Shop link is unavailable.")
            authorize_business_try_on(cast(BusinessTryOnStatus, context["try_on_status"]))
            identity = (
                connection.execute(
                    text(
                        """SELECT channel, normalized_value FROM principal_identities
                        WHERE principal_id=:principal AND account_id=:account
                          AND channel IN ('PHONE', 'EMAIL') AND verified_at IS NOT NULL
                        ORDER BY (channel='PHONE') DESC, created_at
                        LIMIT 1"""
                    ),
                    {"principal": consumer_principal_id, "account": consumer_account_id},
                )
                .mappings()
                .one_or_none()
            )
            if identity is None:
                raise SponsoredTryOnError(
                    "VERIFIED_IDENTITY_REQUIRED",
                    "Verify an email address or mobile number before starting.",
                )
            mobile = identity["normalized_value"] if identity["channel"] == "PHONE" else None
            email = identity["normalized_value"] if identity["channel"] == "EMAIL" else None
            owner_principal_id: UUID = connection.execute(
                text(
                    """SELECT principal_id FROM tenant_memberships
                    WHERE tenant_id=:tenant AND account_id=:account
                      AND role='OWNER' AND revoked_at IS NULL
                    ORDER BY created_at LIMIT 1"""
                ),
                {"tenant": context["tenant_id"], "account": context["business_account_id"]},
            ).scalar_one()
            participant_id: UUID = connection.execute(
                text(
                    """INSERT INTO business_participants
                    (tenant_id, business_account_id, consumer_account_id,
                     consumer_principal_id, normalized_mobile, normalized_email,
                     first_seen_at, latest_seen_at)
                    VALUES (:tenant, :business_account, :consumer_account, :consumer_principal,
                            :mobile, :email, :now, :now)
                    ON CONFLICT (tenant_id, consumer_principal_id) DO UPDATE SET
                      consumer_account_id=EXCLUDED.consumer_account_id,
                      normalized_mobile=EXCLUDED.normalized_mobile,
                      normalized_email=EXCLUDED.normalized_email,
                      latest_seen_at=EXCLUDED.latest_seen_at
                    RETURNING participant_id"""
                ),
                {
                    "tenant": context["tenant_id"],
                    "business_account": context["business_account_id"],
                    "consumer_account": consumer_account_id,
                    "consumer_principal": consumer_principal_id,
                    "mobile": mobile,
                    "email": email,
                    "now": current,
                },
            ).scalar_one()
            connection.execute(
                text(
                    """UPDATE business_sponsored_sessions SET status='EXPIRED', updated_at=:now
                    WHERE tenant_id=:tenant AND consumer_principal_id=:principal
                      AND status IN ('ACTIVE', 'EXHAUSTED') AND expires_at <= :now"""
                ),
                {
                    "tenant": context["tenant_id"],
                    "principal": consumer_principal_id,
                    "now": current,
                },
            )
            existing = (
                connection.execute(
                    text(
                        """SELECT session_id, allowance_limit, try_ons_used, status, expires_at
                        FROM business_sponsored_sessions
                        WHERE tenant_id=:tenant AND consumer_principal_id=:principal
                          AND status IN ('ACTIVE', 'EXHAUSTED') AND expires_at > :now
                        ORDER BY created_at DESC LIMIT 1"""
                    ),
                    {
                        "tenant": context["tenant_id"],
                        "principal": consumer_principal_id,
                        "now": current,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                self._sync_session_allowance(connection, existing["session_id"], current)
                refreshed = (
                    connection.execute(
                        text(
                            """SELECT session_id, allowance_limit, try_ons_used, status, expires_at
                            FROM business_sponsored_sessions WHERE session_id=:session"""
                        ),
                        {"session": existing["session_id"]},
                    )
                    .mappings()
                    .one()
                )
                return self._session(dict(refreshed), context["display_name"])
            if mobile is None:
                allowance_query = text(
                    """SELECT default_try_on_limit
                    FROM business_allowance_policies
                    WHERE tenant_id=:tenant AND account_id=:account"""
                )
                allowance_parameters = {
                    "tenant": context["tenant_id"],
                    "account": context["business_account_id"],
                }
            else:
                allowance_query = text(
                    """SELECT p.default_try_on_limit + COALESCE(u.limit_adjustment, 0)
                        FROM business_allowance_policies p
                        LEFT JOIN business_user_allowances u
                          ON u.tenant_id=p.tenant_id AND u.account_id=p.account_id
                         AND u.normalized_mobile=:mobile
                        WHERE p.tenant_id=:tenant AND p.account_id=:account"""
                )
                allowance_parameters = {
                    "tenant": context["tenant_id"],
                    "account": context["business_account_id"],
                    "mobile": mobile,
                }
            allowance = int(
                connection.execute(allowance_query, allowance_parameters).scalar_one()
            )
            if mobile is not None:
                connection.execute(
                    text(
                        """INSERT INTO business_user_allowances
                    (tenant_id, account_id, normalized_mobile, limit_adjustment, used_count,
                     period_started_at, updated_by_principal_id)
                    VALUES (:tenant, :account, :mobile, 0, 0, :now, :owner)
                    ON CONFLICT (tenant_id, normalized_mobile) DO UPDATE SET
                      period_started_at=CASE
                        WHEN business_user_allowances.period_started_at <= :reset_before
                        THEN :now ELSE business_user_allowances.period_started_at END,
                      used_count=CASE
                        WHEN business_user_allowances.period_started_at <= :reset_before
                        THEN 0 ELSE business_user_allowances.used_count END,
                      updated_at=:now"""
                    ),
                    {
                        "tenant": context["tenant_id"],
                        "account": context["business_account_id"],
                        "mobile": mobile,
                        "now": current,
                        "reset_before": current - self.session_ttl,
                        "owner": owner_principal_id,
                    },
                )
            row = (
                connection.execute(
                    text(
                        """INSERT INTO business_sponsored_sessions
                        (participant_id, tenant_id, business_account_id, consumer_account_id,
                         consumer_principal_id, allowance_limit, expires_at, created_at, updated_at)
                        VALUES (:participant, :tenant, :business_account, :consumer_account,
                                :consumer_principal, :allowance, :expires, :now, :now)
                        RETURNING session_id, allowance_limit, try_ons_used, status, expires_at"""
                    ),
                    {
                        "participant": participant_id,
                        "tenant": context["tenant_id"],
                        "business_account": context["business_account_id"],
                        "consumer_account": consumer_account_id,
                        "consumer_principal": consumer_principal_id,
                        "allowance": max(allowance, 0),
                        "expires": expires_at,
                        "now": current,
                    },
                )
                .mappings()
                .one()
            )
            return self._session(dict(row), context["display_name"])

    def status(
        self, session_id: UUID, consumer_account_id: UUID, consumer_principal_id: UUID
    ) -> dict[str, object]:
        current = datetime.now(UTC)
        with self.engine.begin() as connection:
            self._sync_session_allowance(connection, session_id, current)
            row = (
                connection.execute(
                    text(
                        """SELECT s.session_id, s.allowance_limit, s.try_ons_used, s.status,
                                  s.expires_at, p.display_name, t.try_on_status
                        FROM business_sponsored_sessions s
                        JOIN business_profiles p
                          ON p.tenant_id=s.tenant_id AND p.account_id=s.business_account_id
                        JOIN business_tenants t
                          ON t.tenant_id=s.tenant_id AND t.account_id=s.business_account_id
                        WHERE s.session_id=:session AND s.consumer_account_id=:account
                          AND s.consumer_principal_id=:principal"""
                    ),
                    {
                        "session": session_id,
                        "account": consumer_account_id,
                        "principal": consumer_principal_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SponsoredTryOnError("SESSION_UNAVAILABLE", "Session is unavailable.")
        return self._session(dict(row), row["display_name"])

    def consume(
        self,
        *,
        session_id: UUID,
        consumer_account_id: UUID,
        consumer_principal_id: UUID,
        request_key: str,
        now: datetime | None = None,
    ) -> dict[str, object]:
        key = request_key.strip()
        if not 8 <= len(key) <= 80:
            raise SponsoredTryOnError("INVALID_IDEMPOTENCY_KEY", "A valid request key is required.")
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"sponsored:{session_id}:{key}"},
            )
            self._sync_session_allowance(connection, session_id, current)
            session = (
                connection.execute(
                    text(
                        """SELECT s.*, m.principal_id AS owner_principal_id,
                                  p.normalized_mobile, p.normalized_email, t.try_on_status
                        FROM business_sponsored_sessions s
                        JOIN business_participants p ON p.participant_id=s.participant_id
                        JOIN business_tenants t
                          ON t.tenant_id=s.tenant_id AND t.account_id=s.business_account_id
                        JOIN tenant_memberships m
                          ON m.tenant_id=s.tenant_id AND m.account_id=s.business_account_id
                         AND m.role='OWNER' AND m.revoked_at IS NULL
                        WHERE s.session_id=:session AND s.consumer_account_id=:consumer_account
                          AND s.consumer_principal_id=:consumer_principal
                        ORDER BY m.created_at LIMIT 1 FOR UPDATE OF s"""
                    ),
                    {
                        "session": session_id,
                        "consumer_account": consumer_account_id,
                        "consumer_principal": consumer_principal_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if session is None:
                raise SponsoredTryOnError("SESSION_UNAVAILABLE", "Session is unavailable.")
            operation_key = f"sponsored:{key}"
            existing = (
                connection.execute(
                    text(
                        """SELECT t.sponsored_tryon_id, t.usage_id, u.token_cost
                        FROM business_sponsored_tryons t
                        JOIN billable_usage_records u ON u.usage_id=t.usage_id
                        WHERE t.business_account_id=:account AND t.request_key=:key"""
                    ),
                    {"account": session["business_account_id"], "key": operation_key},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._consumption(dict(existing), dict(session))
            authorize_business_try_on(cast(BusinessTryOnStatus, session["try_on_status"]))
            if session["expires_at"] <= current:
                connection.execute(
                    text(
                        "UPDATE business_sponsored_sessions SET status='EXPIRED', updated_at=:now "
                        "WHERE session_id=:session"
                    ),
                    {"now": current, "session": session_id},
                )
                raise SponsoredTryOnError("SESSION_EXPIRED", "The 24-hour session has expired.")
            if (
                session["status"] != "ACTIVE"
                or session["try_ons_used"] >= session["allowance_limit"]
            ):
                raise SponsoredTryOnError(
                    "TRY_ON_ALLOWANCE_USED", "No try-ons remain in this 24-hour session."
                )
            price = (
                connection.execute(
                    text(
                        """SELECT price_version_id, token_cost FROM price_versions
                        WHERE action_code='TRY_ON' AND effective_from <= :now
                          AND (effective_until IS NULL OR effective_until > :now)
                        ORDER BY effective_from DESC LIMIT 1"""
                    ),
                    {"now": current},
                )
                .mappings()
                .one_or_none()
            )
            if price is None:
                raise SponsoredTryOnError("PRICE_UNAVAILABLE", "Try-on pricing is unavailable.")
            bucket = (
                connection.execute(
                    text(
                        """SELECT b.bucket_id, b.wallet_id FROM wallet_buckets b
                        WHERE b.account_id=:account
                          AND (b.expires_at IS NULL OR b.expires_at > :now)
                          AND (SELECT COALESCE(sum(e.amount), 0) FROM ledger_entries e
                               WHERE e.bucket_id=b.bucket_id AND e.account_id=b.account_id
                                 AND e.entry_type IN
                                     ('CREDIT','DEBIT','RECREDIT','EXPIRY')) >= :cost
                        ORDER BY (b.bucket_type='PROMO') DESC, b.expires_at NULLS LAST
                        LIMIT 1 FOR UPDATE"""
                    ),
                    {
                        "account": session["business_account_id"],
                        "now": current,
                        "cost": price["token_cost"],
                    },
                )
                .mappings()
                .one_or_none()
            )
            if bucket is None:
                raise SponsoredTryOnError(
                    "BUSINESS_TOKENS_UNAVAILABLE", "The business has insufficient Wearo Tokens."
                )
            entry_id, usage_id, sponsored_id = uuid4(), uuid4(), uuid4()
            connection.execute(
                text(
                    """INSERT INTO ledger_entries
                    (entry_id, account_id, tenant_id, wallet_id, bucket_id, entry_type,
                     amount, operation_key, performed_by_principal_id)
                    VALUES (:entry, :account, :tenant, :wallet, :bucket, 'DEBIT', :amount,
                            :key, :owner)"""
                ),
                {
                    "entry": entry_id,
                    "account": session["business_account_id"],
                    "tenant": session["tenant_id"],
                    "wallet": bucket["wallet_id"],
                    "bucket": bucket["bucket_id"],
                    "amount": -int(price["token_cost"]),
                    "key": operation_key,
                    "owner": session["owner_principal_id"],
                },
            )
            connection.execute(
                text(
                    """INSERT INTO billable_usage_records
                    (usage_id, account_id, tenant_id, principal_id, action_code, request_key,
                     price_version_id, token_cost, ledger_entry_id, created_at)
                    VALUES (:usage, :account, :tenant, :owner, 'TRY_ON', :key, :price,
                            :cost, :entry, :now)"""
                ),
                {
                    "usage": usage_id,
                    "account": session["business_account_id"],
                    "tenant": session["tenant_id"],
                    "owner": session["owner_principal_id"],
                    "key": operation_key,
                    "price": price["price_version_id"],
                    "cost": price["token_cost"],
                    "entry": entry_id,
                    "now": current,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO business_sponsored_tryons
                    (sponsored_tryon_id, session_id, tenant_id, business_account_id,
                     request_key, usage_id, created_at)
                    VALUES (:id, :session, :tenant, :account, :key, :usage, :now)"""
                ),
                {
                    "id": sponsored_id,
                    "session": session_id,
                    "tenant": session["tenant_id"],
                    "account": session["business_account_id"],
                    "key": operation_key,
                    "usage": usage_id,
                    "now": current,
                },
            )
            updated = (
                connection.execute(
                    text(
                        """UPDATE business_sponsored_sessions
                        SET try_ons_used=try_ons_used+1,
                            status=CASE WHEN try_ons_used+1 >= allowance_limit
                                        THEN 'EXHAUSTED' ELSE 'ACTIVE' END,
                            updated_at=:now
                        WHERE session_id=:session
                        RETURNING allowance_limit, try_ons_used, status, expires_at"""
                    ),
                    {"session": session_id, "now": current},
                )
                .mappings()
                .one()
            )
            if session["normalized_mobile"] is not None:
                connection.execute(
                    text(
                        """UPDATE business_user_allowances
                        SET used_count=used_count+1, updated_at=:now
                        WHERE tenant_id=:tenant AND normalized_mobile=:mobile"""
                    ),
                    {
                        "tenant": session["tenant_id"],
                        "mobile": session["normalized_mobile"],
                        "now": current,
                    },
                )
            return self._consumption(
                {
                    "sponsored_tryon_id": sponsored_id,
                    "usage_id": usage_id,
                    "token_cost": int(price["token_cost"]),
                },
                dict(updated),
            )

    @staticmethod
    def _session(row: Mapping[str, Any], business_name: object) -> dict[str, object]:
        return {
            "session_id": row["session_id"],
            "business_name": str(business_name),
            "expires_at": row["expires_at"],
            "status": row["status"],
            "business_try_on_status": row.get("try_on_status", "ACTIVE"),
            "try_ons_allotted": int(row["allowance_limit"]),
            "try_ons_used": int(row["try_ons_used"]),
            "try_ons_remaining": max(int(row["allowance_limit"]) - int(row["try_ons_used"]), 0),
        }

    @staticmethod
    def _consumption(usage: Mapping[str, Any], session: Mapping[str, Any]) -> dict[str, object]:
        return {
            "sponsored_tryon_id": usage["sponsored_tryon_id"],
            "usage_id": usage["usage_id"],
            "token_cost": int(usage["token_cost"]),
            "try_ons_remaining": max(
                int(session["allowance_limit"]) - int(session["try_ons_used"]), 0
            ),
            "session_status": session["status"],
            "expires_at": session["expires_at"],
        }
