from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

import razorpay
import requests
from razorpay import errors as razorpay_errors
from sqlalchemy import Connection, Engine, text

from .business_platform import RECOMMENDATIONS, OperatingProfile
from .tenant_scope import TenantScopeError, require_tenant_scope


class TopUpError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GatewayOrder:
    provider_order_id: str
    checkout_url: str
    key_id: str = ""


class PaymentGateway(Protocol):
    key_id: str

    def create_order(
        self, *, order_id: UUID, amount_minor: int, currency: str, idempotency_key: str
    ) -> GatewayOrder: ...


class UnavailablePaymentGateway:
    key_id = ""

    def create_order(self, **_: object) -> GatewayOrder:
        raise TopUpError("PAYMENT_GATEWAY_UNAVAILABLE", "Payment gateway is not configured.")


class HttpPaymentGateway:
    def __init__(self, endpoint: str, api_key: str) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.key_id = ""

    def create_order(
        self, *, order_id: UUID, amount_minor: int, currency: str, idempotency_key: str
    ) -> GatewayOrder:
        try:
            response = requests.post(
                self.endpoint,
                json={
                    "reference": str(order_id),
                    "amount_minor": amount_minor,
                    "currency": currency,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Idempotency-Key": idempotency_key,
                },
                timeout=10,
            )
            response.raise_for_status()
            body = response.json()
            return GatewayOrder(str(body["order_id"]), str(body["checkout_url"]))
        except (requests.RequestException, KeyError, ValueError, TypeError):
            raise TopUpError(
                "PAYMENT_GATEWAY_UNAVAILABLE", "Payment gateway is temporarily unavailable."
            ) from None


class RazorpayPaymentGateway:
    def __init__(self, key_id: str, key_secret: str) -> None:
        self.key_id = key_id
        self.client = razorpay.Client(auth=(key_id, key_secret))

    def create_order(
        self, *, order_id: UUID, amount_minor: int, currency: str, idempotency_key: str
    ) -> GatewayOrder:
        if amount_minor < 100:
            raise TopUpError("INVALID_PAYMENT_AMOUNT", "Payment amount must be at least 100 paise.")
        try:
            result = self.client.order.create(
                {
                    "amount": amount_minor,
                    "currency": currency,
                    "receipt": str(order_id),
                    "notes": {"idempotency_key": idempotency_key},
                }
            )
            return GatewayOrder(str(result["id"]), "", self.key_id)
        except razorpay_errors.BadRequestError as error:
            message = str(error).casefold()
            if "auth" in message or "key" in message:
                raise TopUpError(
                    "PAYMENT_GATEWAY_AUTH_FAILED", "Payment gateway authentication failed."
                ) from None
            raise TopUpError("PAYMENT_ORDER_REJECTED", "Payment order was rejected.") from None
        except (razorpay_errors.GatewayError, razorpay_errors.ServerError, KeyError, TypeError):
            raise TopUpError(
                "PAYMENT_GATEWAY_UNAVAILABLE", "Payment gateway is temporarily unavailable."
            ) from None

    def fetch_payment(self, payment_id: str) -> dict[str, object]:
        try:
            result = self.client.payment.fetch(payment_id)
            if not isinstance(result, dict):
                raise TypeError
            return cast(dict[str, object], result)
        except razorpay_errors.BadRequestError:
            raise TopUpError("PAYMENT_UNAVAILABLE", "Payment could not be verified.") from None
        except (razorpay_errors.GatewayError, razorpay_errors.ServerError, TypeError):
            raise TopUpError(
                "PAYMENT_GATEWAY_UNAVAILABLE", "Payment gateway is temporarily unavailable."
            ) from None

    def fetch_order_payments(self, order_id: str) -> tuple[dict[str, object], ...]:
        try:
            result = self.client.order.payments(order_id)
            items = result.get("items", []) if isinstance(result, dict) else []
            return tuple(cast(dict[str, object], item) for item in items if isinstance(item, dict))
        except razorpay_errors.BadRequestError:
            raise TopUpError("PAYMENT_UNAVAILABLE", "Payment could not be verified.") from None
        except (razorpay_errors.GatewayError, razorpay_errors.ServerError, TypeError):
            raise TopUpError(
                "PAYMENT_GATEWAY_UNAVAILABLE", "Payment gateway is temporarily unavailable."
            ) from None


def verify_webhook_signature(payload: bytes, signature: str | None, secret: bytes) -> None:
    if not signature or not secret:
        raise TopUpError("INVALID_WEBHOOK_SIGNATURE", "Webhook signature is invalid.")
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, supplied):
        raise TopUpError("INVALID_WEBHOOK_SIGNATURE", "Webhook signature is invalid.")


def verify_payment_signature(
    order_id: str, payment_id: str, signature: str, secret: bytes
) -> None:
    if not order_id or not payment_id or not signature or not secret:
        raise TopUpError("INVALID_PAYMENT_SIGNATURE", "Payment verification fields are required.")
    expected = hmac.new(secret, f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise TopUpError("INVALID_PAYMENT_SIGNATURE", "Payment signature is invalid.")


def estimate_try_ons(
    tokens: int, offerings: tuple[str, ...], rates: dict[str, int]
) -> tuple[dict[str, object], ...]:
    estimates: list[dict[str, object]] = []
    for offering in offerings:
        cost = rates.get(f"{offering}_TRY_ON", rates.get("TRY_ON"))
        estimates.append(
            {
                "offering": offering,
                "token_cost": cost,
                "estimated_try_ons": tokens // cost if cost and cost > 0 else None,
            }
        )
    return tuple(estimates)


class PostgresTopUps:
    def __init__(
        self,
        engine: Engine,
        gateway: PaymentGateway,
        webhook_secret: bytes,
        checkout_secret: bytes | None = None,
    ) -> None:
        self.engine = engine
        self.gateway = gateway
        self.webhook_secret = webhook_secret
        self.checkout_secret = checkout_secret if checkout_secret is not None else webhook_secret

    def packs(self, now: datetime | None = None) -> tuple[dict[str, object], ...]:
        current = now or datetime.now(UTC)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT pack_id, code, purchased_tokens, promo_tokens, amount_minor,
                              currency, tax_rate_basis_points
                    FROM token_packs WHERE effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY amount_minor, pack_id"""
                ),
                {"now": current},
            ).mappings()
            return tuple(dict(row) for row in rows)

    def purchase_context(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        now = datetime.now(UTC)
        with self.engine.connect() as connection:
            try:
                account_id = require_tenant_scope(connection, principal_id, tenant_id).account_id
            except TenantScopeError:
                raise TopUpError("TOPUP_UNAVAILABLE", "Resource unavailable.") from None
            profile = cast(
                OperatingProfile,
                connection.execute(
                    text(
                        """SELECT operating_profile FROM business_profiles
                    WHERE tenant_id=:tenant AND account_id=:account"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                ).scalar_one(),
            )
            recommendation = RECOMMENDATIONS[profile]
            rates = {
                row["action_code"]: int(row["token_cost"])
                for row in connection.execute(
                    text(
                        """SELECT action_code, token_cost FROM price_versions
                        WHERE effective_from <= :now
                          AND (effective_until IS NULL OR effective_until > :now)"""
                    ),
                    {"now": now},
                ).mappings()
            }
            balance = int(
                connection.execute(
                    text(
                        """SELECT COALESCE(sum(amount), 0) FROM ledger_entries
                        WHERE account_id=:account"""
                    ),
                    {"account": account_id},
                ).scalar_one()
            )
        items = []
        for pack in self.packs(now):
            purchased = pack["purchased_tokens"]
            promotional = pack["promo_tokens"]
            if not isinstance(purchased, int) or not isinstance(promotional, int):
                raise TopUpError("TOKEN_PACK_UNAVAILABLE", "Token pack is invalid.")
            tokens = purchased + promotional
            items.append(
                {
                    **pack,
                    "total_tokens": tokens,
                    "estimated_try_ons": estimate_try_ons(
                        tokens, recommendation.eligible_offerings, rates
                    ),
                }
            )
        return {
            "eligible": bool(recommendation.eligible_offerings),
            "eligible_offerings": recommendation.eligible_offerings,
            "current_token_balance": balance,
            "current_estimated_try_ons": estimate_try_ons(
                balance, recommendation.eligible_offerings, rates
            ),
            "items": tuple(items),
            "explanation": (
                "Estimates use current published per-action rates. Actual token costs vary by "
                "action and the rate shown before confirmation."
            ),
        }

    def create_order(
        self, principal_id: UUID, tenant_id: UUID, pack_id: UUID, idempotency_key: str
    ) -> dict[str, object]:
        key = idempotency_key.strip()
        if not 8 <= len(key) <= 100:
            raise TopUpError("INVALID_IDEMPOTENCY_KEY", "A valid idempotency key is required.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            try:
                account_id = require_tenant_scope(
                    connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
                ).account_id
            except TenantScopeError:
                raise TopUpError("TOPUP_UNAVAILABLE", "Resource unavailable.") from None
            profile = cast(
                OperatingProfile,
                connection.execute(
                    text(
                        """SELECT operating_profile FROM business_profiles
                    WHERE tenant_id=:tenant AND account_id=:account"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                ).scalar_one(),
            )
            if not RECOMMENDATIONS[profile].eligible_offerings:
                raise TopUpError(
                    "TOPUP_NOT_ELIGIBLE", "This operating profile has no eligible offering."
                )
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"topup:{account_id}:{key}"},
            )
            existing = (
                connection.execute(
                    text(
                        """SELECT payment_order_id, provider_order_id, checkout_url, state,
                              amount_minor, currency
                    FROM payment_orders WHERE account_id = :account AND idempotency_key = :key"""
                    ),
                    {"account": account_id, "key": key},
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                return {**dict(existing), "key_id": self.gateway.key_id}
            pack = (
                connection.execute(
                    text(
                        """SELECT purchased_tokens, promo_tokens, amount_minor, currency,
                              tax_rate_basis_points
                    FROM token_packs WHERE pack_id = :pack AND effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)"""
                    ),
                    {"pack": pack_id, "now": now},
                )
                .mappings()
                .one_or_none()
            )
            if pack is None:
                raise TopUpError("TOKEN_PACK_UNAVAILABLE", "Token pack is unavailable.")
            order_id = uuid4()
            gateway_order = self.gateway.create_order(
                order_id=order_id,
                amount_minor=pack["amount_minor"],
                currency=pack["currency"],
                idempotency_key=key,
            )
            connection.execute(
                text(
                    """INSERT INTO payment_orders
                    (payment_order_id, account_id, tenant_id, pack_id, provider_order_id,
                     checkout_url, idempotency_key, amount_minor, currency, purchased_tokens,
                     promo_tokens, tax_rate_basis_points, state)
                    VALUES (:order, :account, :tenant, :pack, :provider, :checkout, :key,
                            :amount, :currency, :purchased, :promo, :tax_rate, 'PENDING')"""
                ),
                {
                    "order": order_id,
                    "account": account_id,
                    "tenant": tenant_id,
                    "pack": pack_id,
                    "provider": gateway_order.provider_order_id,
                    "checkout": gateway_order.checkout_url,
                    "key": key,
                    "amount": pack["amount_minor"],
                    "currency": pack["currency"],
                    "purchased": pack["purchased_tokens"],
                    "promo": pack["promo_tokens"],
                    "tax_rate": pack["tax_rate_basis_points"],
                },
            )
        return {
            "payment_order_id": order_id,
            "provider_order_id": gateway_order.provider_order_id,
            "checkout_url": gateway_order.checkout_url,
            "key_id": gateway_order.key_id,
            "state": "PENDING",
            "amount_minor": pack["amount_minor"],
            "currency": pack["currency"],
        }

    def create_consumer_order(
        self, account_id: UUID, package_id: UUID, idempotency_key: str
    ) -> dict[str, object]:
        key = idempotency_key.strip()
        if not 8 <= len(key) <= 100:
            raise TopUpError("INVALID_IDEMPOTENCY_KEY", "A valid idempotency key is required.")
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"consumer-topup:{account_id}:{key}"},
            )
            existing = connection.execute(
                text(
                    """SELECT payment_order_id, provider_order_id, checkout_url, state,
                              amount_minor, currency
                       FROM payment_orders
                       WHERE account_id=:account AND idempotency_key=:key"""
                ),
                {"account": account_id, "key": key},
            ).mappings().one_or_none()
            if existing:
                return {**dict(existing), "key_id": self.gateway.key_id}
            package = connection.execute(
                text(
                    """SELECT p.retail_package_id, p.minimum_amount_minor,
                              p.gst_basis_points, p.currency, r.tokens_per_tryon
                       FROM retail_tryon_packages p
                       JOIN retail_tryon_prices r ON r.effective_until IS NULL
                                                AND r.effective_from <= now()
                       WHERE p.retail_package_id=:package AND p.active=true
                       ORDER BY r.effective_from DESC LIMIT 1"""
                ),
                {"package": package_id},
            ).mappings().one_or_none()
            if package is None:
                raise TopUpError("TOKEN_PACK_UNAVAILABLE", "Try-on package is unavailable.")
            base_amount = int(package["minimum_amount_minor"])
            gst_rate = int(package["gst_basis_points"])
            amount_minor = base_amount + round(base_amount * gst_rate / 10_000)
            purchased_tokens = base_amount // 20
            order_id = uuid4()
            gateway_order = self.gateway.create_order(
                order_id=order_id,
                amount_minor=amount_minor,
                currency=str(package["currency"]),
                idempotency_key=key,
            )
            connection.execute(
                text(
                    """INSERT INTO payment_orders
                       (payment_order_id, account_id, retail_package_id, provider_order_id,
                        checkout_url, idempotency_key, amount_minor, currency,
                        purchased_tokens, promo_tokens, tax_rate_basis_points, state)
                       VALUES (:order, :account, :package, :provider, :checkout, :key,
                               :amount, :currency, :tokens, 0, :tax_rate, 'PENDING')"""
                ),
                {
                    "order": order_id,
                    "account": account_id,
                    "package": package_id,
                    "provider": gateway_order.provider_order_id,
                    "checkout": gateway_order.checkout_url,
                    "key": key,
                    "amount": amount_minor,
                    "currency": package["currency"],
                    "tokens": purchased_tokens,
                    "tax_rate": gst_rate,
                },
            )
        return {
            "payment_order_id": order_id,
            "provider_order_id": gateway_order.provider_order_id,
            "key_id": gateway_order.key_id,
            "state": "PENDING",
            "amount_minor": amount_minor,
            "currency": package["currency"],
        }

    def verify_checkout_payment(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        provider_order_id: str,
        provider_payment_id: str,
        signature: str,
    ) -> dict[str, object]:
        with self.engine.connect() as connection:
            try:
                account_id = require_tenant_scope(connection, principal_id, tenant_id).account_id
            except TenantScopeError:
                raise TopUpError(
                    "PAYMENT_ORDER_UNAVAILABLE", "Payment order is unavailable."
                ) from None
            exists = connection.execute(
                text(
                    """SELECT 1 FROM payment_orders
                    WHERE account_id=:account AND tenant_id=:tenant
                      AND provider_order_id=:provider"""
                ),
                {"account": account_id, "tenant": tenant_id, "provider": provider_order_id},
            ).scalar_one_or_none()
        if not exists:
            raise TopUpError("PAYMENT_ORDER_UNAVAILABLE", "Payment order is unavailable.")
        return self._confirm_checkout_payment(provider_order_id, provider_payment_id, signature)

    def verify_consumer_checkout_payment(
        self,
        account_id: UUID,
        provider_order_id: str,
        provider_payment_id: str,
        signature: str,
    ) -> dict[str, object]:
        with self.engine.connect() as connection:
            exists = connection.execute(
                text(
                    """SELECT 1 FROM payment_orders
                       WHERE account_id=:account AND tenant_id IS NULL
                         AND provider_order_id=:provider"""
                ),
                {"account": account_id, "provider": provider_order_id},
            ).scalar_one_or_none()
        if not exists:
            raise TopUpError("PAYMENT_ORDER_UNAVAILABLE", "Payment order is unavailable.")
        return self._confirm_checkout_payment(provider_order_id, provider_payment_id, signature)

    def _confirm_checkout_payment(
        self, provider_order_id: str, provider_payment_id: str, signature: str
    ) -> dict[str, object]:
        verify_payment_signature(
            provider_order_id, provider_payment_id, signature, self.checkout_secret
        )
        fetch_payment = getattr(self.gateway, "fetch_payment", None)
        if not callable(fetch_payment):
            raise TopUpError("PAYMENT_GATEWAY_UNAVAILABLE", "Payment verification is unavailable.")
        payment = fetch_payment(provider_payment_id)
        with self.engine.connect() as connection:
            order = connection.execute(
                text(
                    """SELECT amount_minor, currency FROM payment_orders
                       WHERE provider_order_id=:provider"""
                ),
                {"provider": provider_order_id},
            ).mappings().one_or_none()
        if order is None:
            raise TopUpError("PAYMENT_ORDER_UNAVAILABLE", "Payment order is unavailable.")
        try:
            payment_amount = int(payment.get("amount", -1))
        except (TypeError, ValueError):
            payment_amount = -1
        if (
            str(payment.get("order_id", "")) != provider_order_id
            or str(payment.get("id", "")) != provider_payment_id
            or payment_amount != int(order["amount_minor"])
            or str(payment.get("currency", "")).upper() != str(order["currency"]).upper()
        ):
            raise TopUpError("PAYMENT_DETAILS_MISMATCH", "Payment details do not match the order.")
        if payment.get("captured") is not True and payment.get("status") != "captured":
            return {"success": True, "pending": True, "credited": False}
        result = self._accept_verified_event(
            event_id=f"checkout:{provider_payment_id}",
            provider_order_id=provider_order_id,
            status="CONFIRMED",
            provider_payment_id=provider_payment_id,
        )
        return {"success": True, **result}

    def accept_webhook(
        self, payload: bytes, signature: str | None, event_id_header: str | None = None
    ) -> dict[str, object]:
        verify_webhook_signature(payload, signature, self.webhook_secret)
        try:
            event = json.loads(payload)
            event_name = str(event["event"])
            payment = event.get("payload", {}).get("payment", {}).get("entity", {})
            refund = event.get("payload", {}).get("refund", {}).get("entity", {})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise TopUpError("INVALID_PAYMENT_EVENT", "Payment event is invalid.") from None
        mapping = {
            "payment.captured": "CONFIRMED",
            "order.paid": "CONFIRMED",
            "payment.failed": "FAILED",
            "refund.processed": "REFUNDED",
        }
        status = mapping.get(event_name)
        if status is None:
            return {"accepted": True, "ignored": True}
        provider_order_id = str(payment.get("order_id", ""))
        provider_payment_id = str(payment.get("id", refund.get("payment_id", "")))
        payment_amount = payment.get("amount")
        payment_currency = str(payment.get("currency", ""))
        provider_refund_id = str(refund.get("id", ""))
        refund_amount = refund.get("amount")
        if not provider_order_id or not provider_payment_id:
            raise TopUpError("INVALID_PAYMENT_EVENT", "Payment identifiers are required.")
        if status == "CONFIRMED" and (
            not isinstance(payment_amount, int) or not payment_currency
        ):
            raise TopUpError("INVALID_PAYMENT_EVENT", "Payment amount and currency are required.")
        if status == "REFUNDED" and (
            not provider_refund_id or not isinstance(refund_amount, int)
        ):
            raise TopUpError("INVALID_PAYMENT_EVENT", "Refund details are required.")
        event_id = event_id_header or f"{event_name}:{provider_refund_id or provider_payment_id}"
        return self._accept_verified_event(
            event_id=event_id,
            provider_order_id=provider_order_id,
            status=status,
            provider_payment_id=provider_payment_id,
            provider_refund_id=provider_refund_id,
            refund_amount=refund_amount if isinstance(refund_amount, int) else None,
            payment_amount=payment_amount if isinstance(payment_amount, int) else None,
            payment_currency=payment_currency,
        )

    def _accept_verified_event(
        self,
        *,
        event_id: str,
        provider_order_id: str,
        status: str,
        provider_payment_id: str,
        provider_refund_id: str = "",
        refund_amount: int | None = None,
        payment_amount: int | None = None,
        payment_currency: str = "",
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"payment-event:{event_id}"},
            )
            duplicate = connection.execute(
                text("SELECT payment_event_id FROM payment_events WHERE provider_event_id=:event"),
                {"event": event_id},
            ).scalar_one_or_none()
            if duplicate:
                return {"accepted": True, "duplicate": True}
            order = (
                connection.execute(
                    text(
                        """SELECT * FROM payment_orders
                        WHERE provider_order_id=:provider FOR UPDATE"""
                    ),
                    {"provider": provider_order_id},
                )
                .mappings()
                .one_or_none()
            )
            if order is None:
                raise TopUpError("PAYMENT_ORDER_UNAVAILABLE", "Payment order is unavailable.")
            if status == "CONFIRMED" and (
                payment_amount is not None
                and (
                    payment_amount != int(order["amount_minor"])
                    or payment_currency.upper() != str(order["currency"]).upper()
                )
            ):
                raise TopUpError(
                    "PAYMENT_DETAILS_MISMATCH", "Payment details do not match the order."
                )
            connection.execute(
                text(
                    """INSERT INTO payment_events
                    (account_id, payment_order_id, provider_event_id, event_type, received_at)
                    VALUES (:account, :order, :event, :type, :now)"""
                ),
                {
                    "account": order["account_id"],
                    "order": order["payment_order_id"],
                    "event": event_id,
                    "type": status,
                    "now": now,
                },
            )
            if status == "FAILED":
                if order["state"] != "CONFIRMED":
                    connection.execute(
                        text(
                            """UPDATE payment_orders SET state='FAILED', updated_at=:now
                            WHERE payment_order_id=:order"""
                        ),
                        {"now": now, "order": order["payment_order_id"]},
                    )
                return {"accepted": True, "credited": False}
            if status == "REFUNDED":
                return self._apply_refund(
                    connection,
                    order=dict(order),
                    provider_refund_id=provider_refund_id,
                    amount_minor=refund_amount,
                    now=now,
                )
            if order["state"] == "CONFIRMED":
                return {"accepted": True, "credited": False}
            wallet_id: UUID = connection.execute(
                text(
                    """INSERT INTO wallets (account_id) VALUES (:account)
                    ON CONFLICT (account_id) DO UPDATE SET account_id=EXCLUDED.account_id
                    RETURNING wallet_id"""
                ),
                {"account": order["account_id"]},
            ).scalar_one()
            total = 0
            for bucket_type, amount in (
                ("PURCHASED", order["purchased_tokens"]),
                ("PROMO", order["promo_tokens"]),
            ):
                if not amount:
                    continue
                bucket_id: UUID | None = None
                if bucket_type == "PURCHASED":
                    bucket_id = connection.execute(
                        text(
                            """SELECT bucket_id FROM wallet_buckets
                            WHERE wallet_id=:wallet AND bucket_type='PURCHASED' FOR UPDATE"""
                        ),
                        {"wallet": wallet_id},
                    ).scalar_one_or_none()
                if bucket_id is None:
                    bucket_id = connection.execute(
                        text(
                            """INSERT INTO wallet_buckets (account_id, wallet_id, bucket_type)
                            VALUES (:account, :wallet, :type) RETURNING bucket_id"""
                        ),
                        {"account": order["account_id"], "wallet": wallet_id, "type": bucket_type},
                    ).scalar_one()
                connection.execute(
                    text(
                        """INSERT INTO ledger_entries
                        (account_id, tenant_id, wallet_id, bucket_id,
                         entry_type, amount, operation_key)
                        VALUES (:account, :tenant, :wallet, :bucket, 'CREDIT', :amount, :key)"""
                    ),
                    {
                        "account": order["account_id"],
                        "tenant": order["tenant_id"],
                        "wallet": wallet_id,
                        "bucket": bucket_id,
                        "amount": amount,
                        "key": f"topup:{order['payment_order_id']}:{bucket_type}",
                    },
                )
                total += int(amount)
            receipt_id = uuid4()
            connection.execute(
                text(
                    """INSERT INTO payment_receipts
                    (receipt_id, account_id, payment_order_id, receipt_number,
                     provider_payment_id, amount_minor, currency, tokens_credited, issued_at)
                    VALUES (:receipt, :account, :order, :number, :payment, :amount,
                            :currency, :tokens, :now)"""
                ),
                {
                    "receipt": receipt_id,
                    "account": order["account_id"],
                    "order": order["payment_order_id"],
                    "number": f"WRC-{receipt_id.hex[:16].upper()}",
                    "payment": provider_payment_id,
                    "amount": order["amount_minor"],
                    "currency": order["currency"],
                    "tokens": total,
                    "now": now,
                },
            )
            if order["tenant_id"] is not None:
                profile = (
                    connection.execute(
                        text(
                            """SELECT legal_name, billing_email, billing_address, tax_identifier,
                                  jurisdiction
                            FROM business_profiles
                            WHERE tenant_id=:tenant AND account_id=:account"""
                        ),
                        {"tenant": order["tenant_id"], "account": order["account_id"]},
                    )
                    .mappings()
                    .one()
                )
                rate = int(order["tax_rate_basis_points"] or 0)
                tax_minor = (
                    round(int(order["amount_minor"]) * rate / (10000 + rate)) if rate else 0
                )
                subtotal_minor = int(order["amount_minor"]) - tax_minor
                invoice_id = uuid4()
                connection.execute(
                    text(
                        """INSERT INTO invoices
                        (invoice_id, account_id, tenant_id, payment_order_id, invoice_number,
                         issued_at, subtotal_minor, tax_minor, amount_minor, currency,
                         business_snapshot, tax_snapshot, document_url)
                        VALUES (:invoice, :account, :tenant, :order, :number, :now, :subtotal,
                                :tax, :total, :currency, CAST(:business AS jsonb),
                                CAST(:tax_snapshot AS jsonb), :document_url)"""
                    ),
                    {
                        "invoice": invoice_id,
                        "account": order["account_id"],
                        "tenant": order["tenant_id"],
                        "order": order["payment_order_id"],
                        "number": f"WINV-{now:%Y%m}-{invoice_id.hex[:12].upper()}",
                        "now": now,
                        "subtotal": subtotal_minor,
                        "tax": tax_minor,
                        "total": order["amount_minor"],
                        "currency": order["currency"],
                        "business": json.dumps(dict(profile)),
                        "tax_snapshot": json.dumps(
                            {
                                "rate_basis_points": rate,
                                "tax_minor": tax_minor,
                                "tax_inclusive": True,
                            }
                        ),
                        "document_url": (
                            f"/api/v1/business/tenants/{order['tenant_id']}"
                            f"/invoices/{invoice_id}.txt"
                        ),
                    },
                )
            connection.execute(
                text(
                    """UPDATE payment_orders SET state='CONFIRMED', updated_at=:now
                    WHERE payment_order_id=:order"""
                ),
                {"now": now, "order": order["payment_order_id"]},
            )
            if order["tenant_id"] is not None:
                connection.execute(
                    text(
                        """UPDATE business_subscriptions
                        SET state='ACTIVE', next_billing_at=CASE
                              WHEN next_billing_at IS NULL OR next_billing_at < :now
                              THEN :now + INTERVAL '1 month' ELSE next_billing_at END,
                            trial_ends_at=NULL, updated_at=:now
                        WHERE tenant_id=:tenant AND account_id=:account"""
                    ),
                    {"now": now, "tenant": order["tenant_id"], "account": order["account_id"]},
                )
            connection.execute(
                text(
                    """INSERT INTO audit_events
                    (account_id, tenant_id, actor_type, action, target_type,
                     target_id, reason, occurred_at)
                    VALUES (:account, :tenant, 'SYSTEM', 'WALLET_TOPUP_CREDITED',
                            'PAYMENT_ORDER', :order,
                            'Gateway-confirmed payment credited the wallet.', :now)"""
                ),
                {
                    "account": order["account_id"],
                    "tenant": order["tenant_id"],
                    "order": order["payment_order_id"],
                    "now": now,
                },
            )
        return {"accepted": True, "credited": True, "receipt_id": receipt_id}

    @staticmethod
    def _apply_refund(
        connection: Connection,
        *,
        order: dict[str, object],
        provider_refund_id: str,
        amount_minor: int,
        now: datetime,
    ) -> dict[str, object]:
        execute = connection.execute
        if order["state"] == "REFUNDED":
            return {"accepted": True, "refunded": False, "duplicate": True}
        if order["state"] != "CONFIRMED" or amount_minor != order["amount_minor"]:
            refund_id = uuid4()
            execute(
                text(
                    """INSERT INTO payment_refunds
                    (refund_id, account_id, payment_order_id, provider_refund_id,
                     amount_minor, tokens_reversed, status)
                    VALUES (:refund, :account, :order, :provider, :amount, 0, 'DISCREPANCY')
                    ON CONFLICT (payment_order_id) DO UPDATE SET
                        provider_refund_id=EXCLUDED.provider_refund_id,
                        amount_minor=EXCLUDED.amount_minor,
                        status='DISCREPANCY', updated_at=:now"""
                ),
                {
                    "refund": refund_id,
                    "account": order["account_id"],
                    "order": order["payment_order_id"],
                    "provider": provider_refund_id,
                    "amount": amount_minor,
                    "now": now,
                },
            )
            execute(
                text(
                    """INSERT INTO payment_reconciliation_cases
                    (account_id, payment_order_id, kind, detail)
                    VALUES (:account, :order, 'REFUND_MISMATCH', :detail)"""
                ),
                {
                    "account": order["account_id"],
                    "order": order["payment_order_id"],
                    "detail": "Refund amount or payment state did not match the confirmed order.",
                },
            )
            return {"accepted": True, "refunded": False, "discrepancy": True}
        credits = execute(
            text(
                """SELECT wallet_id, bucket_id, amount, operation_key
                FROM ledger_entries WHERE account_id=:account AND entry_type='CREDIT'
                  AND operation_key LIKE :operation"""
            ),
            {"account": order["account_id"], "operation": f"topup:{order['payment_order_id']}:%"},
        ).mappings()
        reversed_tokens = 0
        for credit in credits:
            execute(
                text(
                    """INSERT INTO ledger_entries
                    (account_id, tenant_id, wallet_id, bucket_id, entry_type, amount, operation_key)
                    VALUES (:account, :tenant, :wallet, :bucket, 'DEBIT', :amount, :key)"""
                ),
                {
                    "account": order["account_id"],
                    "tenant": order["tenant_id"],
                    "wallet": credit["wallet_id"],
                    "bucket": credit["bucket_id"],
                    "amount": -int(credit["amount"]),
                    "key": f"refund:{order['payment_order_id']}:{credit['bucket_id']}",
                },
            )
            reversed_tokens += int(credit["amount"])
        execute(
            text(
                """INSERT INTO payment_refunds
                (account_id, payment_order_id, provider_refund_id, amount_minor,
                 tokens_reversed, status)
                VALUES (:account, :order, :provider, :amount, :tokens, 'RESOLVED')
                ON CONFLICT (payment_order_id) DO UPDATE SET
                    provider_refund_id=EXCLUDED.provider_refund_id,
                    amount_minor=EXCLUDED.amount_minor,
                    tokens_reversed=EXCLUDED.tokens_reversed,
                    status='RESOLVED', updated_at=:now"""
            ),
            {
                "account": order["account_id"],
                "order": order["payment_order_id"],
                "provider": provider_refund_id,
                "amount": amount_minor,
                "tokens": reversed_tokens,
                "now": now,
            },
        )
        execute(
            text(
                """UPDATE payment_orders SET state='REFUNDED', updated_at=:now
                WHERE payment_order_id=:order"""
            ),
            {"now": now, "order": order["payment_order_id"]},
        )
        execute(
            text(
                "UPDATE invoices SET status='VOIDED', updated_at=:now WHERE payment_order_id=:order"
            ),
            {"now": now, "order": order["payment_order_id"]},
        )
        execute(
            text(
                """UPDATE payment_reconciliation_cases
                SET status='RESOLVED', resolved_at=:now, updated_at=:now
                WHERE payment_order_id=:order AND status='OPEN'"""
            ),
            {"now": now, "order": order["payment_order_id"]},
        )
        execute(
            text(
                """INSERT INTO audit_events
                (account_id, tenant_id, actor_type, action, target_type,
                 target_id, reason, occurred_at)
                VALUES (:account, :tenant, 'SYSTEM', 'WALLET_REFUND_REVERSED',
                        'PAYMENT_ORDER', :order,
                        'Gateway-confirmed refund reversed the original wallet credit.', :now)"""
            ),
            {
                "account": order["account_id"],
                "tenant": order["tenant_id"],
                "order": order["payment_order_id"],
                "now": now,
            },
        )
        return {"accepted": True, "refunded": True, "tokens_reversed": reversed_tokens}

    def consumer_billing_history(self, account_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT o.payment_order_id, o.state, o.amount_minor, o.currency,
                              o.purchased_tokens + o.promo_tokens AS tokens,
                              o.created_at, o.updated_at, p.name AS package_name,
                              r.receipt_id, r.receipt_number, r.provider_payment_id,
                              r.issued_at AS paid_at,
                              f.provider_refund_id, f.status AS refund_status
                       FROM payment_orders o
                       LEFT JOIN retail_tryon_packages p
                         ON p.retail_package_id=o.retail_package_id
                       LEFT JOIN payment_receipts r
                         ON r.payment_order_id=o.payment_order_id
                       LEFT JOIN payment_refunds f
                         ON f.payment_order_id=o.payment_order_id
                       WHERE o.account_id=:account AND o.tenant_id IS NULL
                       ORDER BY o.created_at DESC
                       LIMIT 100"""
                ),
                {"account": account_id},
            ).mappings()
            return {"items": tuple(dict(row) for row in rows)}

    def consumer_order_status(self, account_id: UUID, payment_order_id: UUID) -> dict[str, object]:
        def read_order() -> dict[str, object] | None:
            with self.engine.connect() as connection:
                current = connection.execute(
                    text(
                        """SELECT o.payment_order_id, o.provider_order_id, o.state,
                                  o.amount_minor, o.currency,
                                  o.purchased_tokens + o.promo_tokens AS tokens,
                                  r.receipt_id, r.receipt_number, r.issued_at AS paid_at
                           FROM payment_orders o
                           LEFT JOIN payment_receipts r
                             ON r.payment_order_id=o.payment_order_id
                           WHERE o.payment_order_id=:order AND o.account_id=:account
                             AND o.tenant_id IS NULL"""
                    ),
                    {"order": payment_order_id, "account": account_id},
                ).mappings().one_or_none()
            return dict(current) if current else None

        row = read_order()
        if row is None:
            raise TopUpError("PAYMENT_ORDER_UNAVAILABLE", "Payment order is unavailable.")
        fetch_order_payments = getattr(self.gateway, "fetch_order_payments", None)
        if row["state"] in {"PENDING", "FAILED"} and callable(fetch_order_payments):
            payments = fetch_order_payments(str(row["provider_order_id"]))
            captured = next(
                (
                    payment
                    for payment in payments
                    if (payment.get("captured") is True or payment.get("status") == "captured")
                    and str(payment.get("order_id", "")) == str(row["provider_order_id"])
                    and int(payment.get("amount", -1)) == int(row["amount_minor"])
                    and str(payment.get("currency", "")).upper()
                    == str(row["currency"]).upper()
                ),
                None,
            )
            if captured and captured.get("id"):
                self._accept_verified_event(
                    event_id=f"reconcile:{captured['id']}",
                    provider_order_id=str(row["provider_order_id"]),
                    status="CONFIRMED",
                    provider_payment_id=str(captured["id"]),
                    payment_amount=int(captured["amount"]),
                    payment_currency=str(captured["currency"]),
                )
                row = read_order()
                if row is None:
                    raise TopUpError("PAYMENT_ORDER_UNAVAILABLE", "Payment order is unavailable.")
        row.pop("provider_order_id", None)
        return row

    def reconciliation(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            try:
                account_id = require_tenant_scope(connection, principal_id, tenant_id).account_id
            except TenantScopeError:
                raise TopUpError("RECONCILIATION_UNAVAILABLE", "Resource unavailable.") from None
            rows = connection.execute(
                text(
                    """SELECT o.payment_order_id, o.state AS payment_status,
                              i.status AS invoice_status, r.status AS refund_status,
                              r.amount_minor AS refund_amount_minor, r.tokens_reversed,
                              c.kind AS discrepancy_kind, c.status AS discrepancy_status
                    FROM payment_orders o
                    LEFT JOIN invoices i ON i.payment_order_id=o.payment_order_id
                    LEFT JOIN payment_refunds r ON r.payment_order_id=o.payment_order_id
                    LEFT JOIN payment_reconciliation_cases c
                      ON c.payment_order_id=o.payment_order_id AND c.status='OPEN'
                    WHERE o.account_id=:account AND o.tenant_id=:tenant
                    ORDER BY o.created_at DESC"""
                ),
                {"account": account_id, "tenant": tenant_id},
            ).mappings()
            return {"items": tuple(dict(row) for row in rows)}

    def receipt(self, principal_id: UUID, tenant_id: UUID, receipt_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            try:
                account_id = require_tenant_scope(connection, principal_id, tenant_id).account_id
            except TenantScopeError:
                raise TopUpError("RECEIPT_UNAVAILABLE", "Resource unavailable.") from None
            row = (
                connection.execute(
                    text(
                        """SELECT receipt_number, provider_payment_id, amount_minor, currency,
                              tokens_credited, issued_at
                    FROM payment_receipts WHERE receipt_id=:receipt AND account_id=:account"""
                    ),
                    {"receipt": receipt_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise TopUpError("RECEIPT_UNAVAILABLE", "Resource unavailable.")
            return dict(row)

    def invoice(self, principal_id: UUID, tenant_id: UUID, invoice_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            try:
                account_id = require_tenant_scope(connection, principal_id, tenant_id).account_id
            except TenantScopeError:
                raise TopUpError("INVOICE_UNAVAILABLE", "Resource unavailable.") from None
            row = (
                connection.execute(
                    text(
                        """SELECT invoice_number, issued_at, subtotal_minor, tax_minor,
                              amount_minor, currency, business_snapshot, tax_snapshot
                    FROM invoices WHERE invoice_id=:invoice AND account_id=:account
                      AND tenant_id=:tenant"""
                    ),
                    {"invoice": invoice_id, "account": account_id, "tenant": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise TopUpError("INVOICE_UNAVAILABLE", "Resource unavailable.")
            return dict(row)
