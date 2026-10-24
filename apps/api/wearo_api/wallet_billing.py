from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .paying_context import paying_context


class WalletBillingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BillableUsage:
    usage_id: UUID
    account_id: UUID
    tenant_id: UUID | None
    principal_id: UUID
    action_code: str
    request_key: str
    price_version_id: UUID
    token_cost: int
    ledger_entry_id: UUID
    created_at: datetime


RecreditReason = Literal["FAILED", "CANCELLED_BEFORE_PROCESSING", "NON_DELIVERED"]


@dataclass(frozen=True)
class UsageRecredit:
    recredit_id: UUID
    usage_id: UUID
    account_id: UUID
    tenant_id: UUID | None
    reason_code: RecreditReason
    token_amount: int
    ledger_entry_id: UUID
    created_at: datetime


def automatic_recredit_reason(
    outcome: str, *, processing_started: bool, delivered: bool
) -> RecreditReason | None:
    if delivered:
        return None
    if outcome == "FAILED":
        return "FAILED"
    if outcome == "CANCELLED" and not processing_started:
        return "CANCELLED_BEFORE_PROCESSING"
    if outcome == "NON_DELIVERED":
        return "NON_DELIVERED"
    return None


def validate_request_key(value: str) -> str:
    key = value.strip()
    if not 8 <= len(key) <= 100:
        raise WalletBillingError("INVALID_IDEMPOTENCY_KEY", "A valid idempotency key is required.")
    return key


class PostgresWalletBilling:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _usage(row: object) -> BillableUsage:
        value = row._mapping  # type: ignore[attr-defined]
        return BillableUsage(
            **{field: value[field] for field in BillableUsage.__dataclass_fields__}
        )

    def debit_once(
        self,
        *,
        account_id: UUID,
        tenant_id: UUID | None,
        principal_id: UUID,
        action_code: str,
        request_key: str,
        now: datetime | None = None,
    ) -> BillableUsage:
        key = validate_request_key(request_key)
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"{account_id}:{key}"},
            )
            existing = connection.execute(
                text(
                    """
                    SELECT usage_id, account_id, tenant_id, principal_id, action_code,
                           request_key, price_version_id, token_cost, ledger_entry_id, created_at
                    FROM billable_usage_records
                    WHERE account_id = :account AND request_key = :key
                    """
                ),
                {"account": account_id, "key": key},
            ).one_or_none()
            if existing is not None:
                return self._usage(existing)
            owner = connection.execute(
                text(
                    """
                    SELECT a.kind FROM accounts a JOIN principals p ON p.account_id = a.account_id
                    WHERE a.account_id = :account AND p.principal_id = :principal
                      AND a.status = 'ACTIVE' AND p.status = 'ACTIVE'
                    """
                ),
                {"account": account_id, "principal": principal_id},
            ).scalar_one_or_none()
            if owner is None:
                raise WalletBillingError("PAYER_UNAVAILABLE", "Paying context is unavailable.")
            paying_context(owner, account_id, tenant_id)
            price = (
                connection.execute(
                    text(
                        """
                    SELECT price_version_id, token_cost FROM price_versions
                    WHERE action_code = :action AND effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY effective_from DESC LIMIT 1
                    """
                    ),
                    {"action": action_code, "now": current},
                )
                .mappings()
                .one_or_none()
            )
            if price is None:
                raise WalletBillingError("PRICE_UNAVAILABLE", "No published action rate exists.")
            bucket = (
                connection.execute(
                    text(
                        """
                    SELECT b.bucket_id, b.wallet_id
                    FROM wallet_buckets b
                    WHERE b.account_id = :account
                      AND (b.expires_at IS NULL OR b.expires_at > :now)
                      AND (SELECT COALESCE(sum(e.amount), 0) FROM ledger_entries e
                           WHERE e.bucket_id = b.bucket_id AND e.account_id = b.account_id
                             AND e.entry_type IN
                                 ('CREDIT', 'DEBIT', 'RECREDIT', 'EXPIRY')) >= :cost
                    ORDER BY (b.bucket_type = 'PROMO') DESC, b.expires_at NULLS LAST
                    LIMIT 1 FOR UPDATE
                    """
                    ),
                    {"account": account_id, "now": current, "cost": price["token_cost"]},
                )
                .mappings()
                .one_or_none()
            )
            if bucket is None:
                raise WalletBillingError("INSUFFICIENT_TOKENS", "Insufficient Wearo Tokens.")
            entry_id, usage_id = uuid4(), uuid4()
            connection.execute(
                text(
                    """
                    INSERT INTO ledger_entries
                        (entry_id, account_id, tenant_id, wallet_id, bucket_id, entry_type,
                         amount, operation_key, performed_by_principal_id)
                    VALUES
                        (:entry, :account, :tenant, :wallet, :bucket, 'DEBIT',
                         :amount, :key, :principal)
                    """
                ),
                {
                    "entry": entry_id,
                    "account": account_id,
                    "tenant": tenant_id,
                    "wallet": bucket["wallet_id"],
                    "bucket": bucket["bucket_id"],
                    "amount": -int(price["token_cost"]),
                    "key": key,
                    "principal": principal_id,
                },
            )
            row = connection.execute(
                text(
                    """
                    INSERT INTO billable_usage_records
                        (usage_id, account_id, tenant_id, principal_id, action_code,
                         request_key, price_version_id, token_cost, ledger_entry_id, created_at)
                    VALUES
                        (:usage, :account, :tenant, :principal, :action, :key,
                         :price, :cost, :entry, :now)
                    RETURNING usage_id, account_id, tenant_id, principal_id, action_code,
                              request_key, price_version_id, token_cost, ledger_entry_id, created_at
                    """
                ),
                {
                    "usage": usage_id,
                    "account": account_id,
                    "tenant": tenant_id,
                    "principal": principal_id,
                    "action": action_code,
                    "key": key,
                    "price": price["price_version_id"],
                    "cost": price["token_cost"],
                    "entry": entry_id,
                    "now": current,
                },
            ).one()
        return self._usage(row)

    def recredit_once(
        self,
        *,
        account_id: UUID,
        usage_id: UUID,
        reason_code: RecreditReason,
        now: datetime | None = None,
    ) -> UsageRecredit:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"recredit:{account_id}:{usage_id}"},
            )
            existing = (
                connection.execute(
                    text(
                        """
                    SELECT recredit_id, usage_id, account_id, tenant_id, reason_code,
                           token_amount, ledger_entry_id, created_at
                    FROM usage_recredits
                    WHERE usage_id = :usage AND account_id = :account
                    """
                    ),
                    {"usage": usage_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return UsageRecredit(**existing)
            usage = (
                connection.execute(
                    text(
                        """
                    SELECT u.tenant_id, u.token_cost, e.wallet_id, e.bucket_id
                    FROM billable_usage_records u
                    JOIN ledger_entries e
                      ON e.entry_id = u.ledger_entry_id AND e.account_id = u.account_id
                    WHERE u.usage_id = :usage AND u.account_id = :account
                    FOR UPDATE OF u
                    """
                    ),
                    {"usage": usage_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if usage is None:
                raise WalletBillingError("USAGE_UNAVAILABLE", "Billable usage is unavailable.")
            entry_id, recredit_id = uuid4(), uuid4()
            connection.execute(
                text(
                    """
                    INSERT INTO ledger_entries
                        (entry_id, account_id, tenant_id, wallet_id, bucket_id,
                         entry_type, amount, operation_key)
                    VALUES
                        (:entry, :account, :tenant, :wallet, :bucket,
                         'RECREDIT', :amount, :key)
                    """
                ),
                {
                    "entry": entry_id,
                    "account": account_id,
                    "tenant": usage["tenant_id"],
                    "wallet": usage["wallet_id"],
                    "bucket": usage["bucket_id"],
                    "amount": usage["token_cost"],
                    "key": f"recredit:{usage_id}",
                },
            )
            row = (
                connection.execute(
                    text(
                        """
                    INSERT INTO usage_recredits
                        (recredit_id, usage_id, account_id, tenant_id, reason_code,
                         token_amount, ledger_entry_id, created_at)
                    VALUES
                        (:recredit, :usage, :account, :tenant, :reason,
                         :amount, :entry, :now)
                    RETURNING recredit_id, usage_id, account_id, tenant_id, reason_code,
                              token_amount, ledger_entry_id, created_at
                    """
                    ),
                    {
                        "recredit": recredit_id,
                        "usage": usage_id,
                        "account": account_id,
                        "tenant": usage["tenant_id"],
                        "reason": reason_code,
                        "amount": usage["token_cost"],
                        "entry": entry_id,
                        "now": current,
                    },
                )
                .mappings()
                .one()
            )
        return UsageRecredit(**row)

    def settle_outcome(
        self,
        *,
        account_id: UUID,
        usage_id: UUID,
        outcome: str,
        processing_started: bool,
        delivered: bool,
        now: datetime | None = None,
    ) -> UsageRecredit | None:
        """Automatically reverse an eligible terminal usage outcome exactly once."""
        reason = automatic_recredit_reason(
            outcome,
            processing_started=processing_started,
            delivered=delivered,
        )
        if reason is None:
            return None
        return self.recredit_once(
            account_id=account_id,
            usage_id=usage_id,
            reason_code=reason,
            now=now,
        )
