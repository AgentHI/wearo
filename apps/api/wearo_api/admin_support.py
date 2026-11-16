from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .admin_organizations import ADMIN_ACTOR_ID
from .email_otp import normalize_destination, normalize_email


class AdminSupportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_support_identity(value: str) -> tuple[str, str]:
    query = value.strip()
    if not query:
        raise AdminSupportError("INVALID_SUPPORT_SEARCH", "Enter an email address or phone number.")
    channel = "EMAIL" if "@" in query else "PHONE"
    normalized = normalize_email(query) if channel == "EMAIL" else normalize_destination(query)
    if not normalized:
        raise AdminSupportError(
            "INVALID_SUPPORT_SEARCH", "Enter a valid email address or phone number."
        )
    return channel, normalized


class PostgresAdminSupport:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def search(self, identity: str) -> dict[str, object]:
        channel, normalized = normalize_support_identity(identity)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT principal.account_id, principal.principal_id,
                           account.kind AS account_kind, account.status AS account_status,
                           principal.principal_type, principal.status AS principal_status,
                           identity.channel, identity.normalized_value,
                           tenant.tenant_id, tenant.slug AS business_slug,
                           profile.display_name AS business_name,
                           EXISTS (
                             SELECT 1 FROM business_participants participant
                             WHERE participant.consumer_account_id=principal.account_id
                               AND participant.consumer_principal_id=principal.principal_id
                           ) AS is_b2b2c,
                           COALESCE((
                             SELECT sum(entry.amount) FROM ledger_entries entry
                             WHERE entry.account_id=principal.account_id
                           ), 0) AS token_balance
                    FROM principal_identities identity
                    JOIN principals principal
                      ON principal.principal_id=identity.principal_id
                     AND principal.account_id=identity.account_id
                    JOIN accounts account ON account.account_id=principal.account_id
                    LEFT JOIN business_tenants tenant
                      ON tenant.account_id=principal.account_id
                    LEFT JOIN business_profiles profile
                      ON profile.account_id=tenant.account_id
                     AND profile.tenant_id=tenant.tenant_id
                    WHERE identity.channel=:channel AND identity.normalized_value=:identity
                    ORDER BY account.kind, principal.created_at
                    """
                ),
                {"channel": channel, "identity": normalized},
            ).mappings()
            results = []
            for row in rows:
                item = dict(row)
                latest_payment = self._latest_payment(connection, row["account_id"])
                item["customer_type"] = self._customer_type(item)
                item["latest_payment"] = latest_payment
                item["try_ons_remaining"] = self._try_ons(connection, int(row["token_balance"]))
                results.append(item)
        return {"channel": channel, "normalized_identity": normalized, "results": results}

    def add_tokens(self, account_id: UUID, amount: int, reason: str) -> dict[str, object]:
        explanation = reason.strip()
        if not explanation:
            raise AdminSupportError("INVALID_TOKEN_CREDIT", "A support reason is required.")
        if amount <= 0 or amount > 1_000_000:
            raise AdminSupportError(
                "INVALID_TOKEN_CREDIT", "Token credit must be between 1 and 1,000,000."
            )
        now, entry_id = datetime.now(UTC), uuid4()
        with self.engine.begin() as connection:
            account = (
                connection.execute(
                    text(
                        """SELECT account.account_id, account.kind, tenant.tenant_id
                       FROM accounts account
                       LEFT JOIN business_tenants tenant ON tenant.account_id=account.account_id
                       WHERE account.account_id=:account FOR UPDATE"""
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if account is None:
                raise AdminSupportError("SUPPORT_ACCOUNT_NOT_FOUND", "Customer account not found.")
            before = int(
                connection.execute(
                    text(
                        "SELECT COALESCE(sum(amount), 0) FROM ledger_entries "
                        "WHERE account_id=:account"
                    ),
                    {"account": account_id},
                ).scalar_one()
            )
            wallet_id: UUID = connection.execute(
                text(
                    """INSERT INTO wallets (account_id) VALUES (:account)
                       ON CONFLICT (account_id) DO UPDATE SET account_id=EXCLUDED.account_id
                       RETURNING wallet_id"""
                ),
                {"account": account_id},
            ).scalar_one()
            bucket_id: UUID | None = connection.execute(
                text(
                    """SELECT bucket_id FROM wallet_buckets
                       WHERE account_id=:account AND wallet_id=:wallet
                         AND bucket_type='PURCHASED' AND expires_at IS NULL
                       ORDER BY created_at LIMIT 1 FOR UPDATE"""
                ),
                {"account": account_id, "wallet": wallet_id},
            ).scalar_one_or_none()
            if bucket_id is None:
                bucket_id = connection.execute(
                    text(
                        """INSERT INTO wallet_buckets
                           (account_id, wallet_id, bucket_type)
                           VALUES (:account, :wallet, 'PURCHASED') RETURNING bucket_id"""
                    ),
                    {"account": account_id, "wallet": wallet_id},
                ).scalar_one()
            connection.execute(
                text(
                    """INSERT INTO ledger_entries
                       (entry_id, account_id, tenant_id, wallet_id, bucket_id, entry_type,
                        amount, operation_key)
                       VALUES (:entry, :account, :tenant, :wallet, :bucket, 'CREDIT',
                               :amount, :operation_key)"""
                ),
                {
                    "entry": entry_id,
                    "account": account_id,
                    "tenant": account["tenant_id"],
                    "wallet": wallet_id,
                    "bucket": bucket_id,
                    "amount": amount,
                    "operation_key": f"admin-support-credit:{entry_id}",
                },
            )
            after = before + amount
            connection.execute(
                text(
                    """INSERT INTO audit_events
                       (audit_event_id, account_id, tenant_id, actor_type, actor_id, action,
                        target_type, target_id, reason, before_summary, after_summary, occurred_at)
                       VALUES (:event, :account, :tenant, 'ADMIN', :actor,
                               'ADMIN_SUPPORT_TOKEN_CREDIT', 'ACCOUNT', :account, :reason,
                               CAST(:before AS jsonb), CAST(:after AS jsonb), :now)"""
                ),
                {
                    "event": uuid4(),
                    "account": account_id,
                    "tenant": account["tenant_id"],
                    "actor": ADMIN_ACTOR_ID,
                    "reason": explanation,
                    "before": json.dumps({"token_balance": before}),
                    "after": json.dumps({"token_balance": after, "tokens_added": amount}),
                    "now": now,
                },
            )
            try_ons = self._try_ons(connection, after)
        return {
            "account_id": account_id,
            "tokens_added": amount,
            "token_balance": after,
            "try_ons_remaining": try_ons,
        }

    @staticmethod
    def _customer_type(row: dict[str, object]) -> str:
        if row["account_kind"] == "TENANT":
            return "B2B"
        if row["is_b2b2c"]:
            return "B2B2C"
        return "B2C"

    @staticmethod
    def _try_ons(connection: object, tokens: int) -> int | None:
        rate = connection.execute(  # type: ignore[attr-defined]
            text(
                """SELECT tokens_per_tryon FROM retail_tryon_prices
                   WHERE effective_from <= now() AND effective_until IS NULL
                   ORDER BY effective_from DESC LIMIT 1"""
            )
        ).scalar_one_or_none()
        return max(tokens, 0) // int(rate) if rate else None

    @staticmethod
    def _latest_payment(connection: object, account_id: UUID) -> dict[str, object] | None:
        row = (
            connection.execute(  # type: ignore[attr-defined]
                text(
                    """SELECT payment.payment_order_id, payment.state, payment.amount_minor,
                          payment.currency,
                          payment.purchased_tokens + payment.promo_tokens AS tokens,
                          payment.created_at, payment.updated_at, receipt.receipt_number,
                          receipt.provider_payment_id, receipt.issued_at AS paid_at,
                          package.name AS package_name,
                          CASE WHEN price.tokens_per_tryon > 0
                               THEN (payment.purchased_tokens + payment.promo_tokens)
                                    / price.tokens_per_tryon END AS number_of_try_ons
                   FROM payment_orders payment
                   LEFT JOIN payment_receipts receipt
                     ON receipt.payment_order_id=payment.payment_order_id
                   LEFT JOIN retail_tryon_packages package
                     ON package.retail_package_id=payment.retail_package_id
                   LEFT JOIN LATERAL (
                     SELECT tokens_per_tryon FROM retail_tryon_prices
                     WHERE effective_from <= payment.created_at
                       AND (effective_until IS NULL OR effective_until > payment.created_at)
                     ORDER BY effective_from DESC LIMIT 1
                   ) price ON true
                   WHERE payment.account_id=:account
                   ORDER BY payment.created_at DESC LIMIT 1"""
                ),
                {"account": account_id},
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row else None
