import hashlib
import hmac
from contextlib import AbstractContextManager
from typing import Any, cast
from uuid import uuid4

import pytest

from apps.api.wearo_api.topups import (
    PostgresTopUps,
    TopUpError,
    UnavailablePaymentGateway,
    estimate_try_ons,
    verify_payment_signature,
    verify_webhook_signature,
)


class BillingRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> "BillingRows":
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


class BillingConnection(AbstractContextManager["BillingConnection"]):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.parameters: dict[str, object] = {}

    def __enter__(self) -> "BillingConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, _: object, parameters: dict[str, object]) -> BillingRows:
        self.parameters = parameters
        return BillingRows(self.rows)


class BillingEngine:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.connection = BillingConnection(rows)

    def connect(self) -> BillingConnection:
        return self.connection


def test_consumer_billing_history_returns_a_bounded_page_with_continuation() -> None:
    engine = BillingEngine([{"payment_order_id": uuid4()} for _ in range(3)])
    service = PostgresTopUps(cast(Any, engine), UnavailablePaymentGateway(), b"webhook-secret")

    result = service.consumer_billing_history(uuid4(), page=2, page_size=2)

    items = cast(tuple[dict[str, object], ...], result["items"])
    assert len(items) == 2
    assert result["page"] == 2
    assert result["page_size"] == 2
    assert result["has_previous"] is True
    assert result["has_next"] is True
    assert engine.connection.parameters["limit"] == 3
    assert engine.connection.parameters["offset"] == 2


@pytest.mark.parametrize(("page", "page_size"), [(0, 10), (1, 0), (1, 51)])
def test_consumer_billing_history_rejects_invalid_pages(page: int, page_size: int) -> None:
    service = PostgresTopUps(
        cast(Any, BillingEngine([])), UnavailablePaymentGateway(), b"webhook-secret"
    )

    with pytest.raises(TopUpError) as raised:
        service.consumer_billing_history(uuid4(), page=page, page_size=page_size)

    assert raised.value.code == "INVALID_PAGE"


def test_valid_gateway_signature_is_accepted() -> None:
    payload = b'{"event_id":"evt-1","status":"CONFIRMED"}'
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    verify_webhook_signature(payload, f"sha256={signature}", b"secret")


@pytest.mark.parametrize("signature", [None, "sha256=wrong"])
def test_missing_or_invalid_gateway_signature_is_rejected(signature: str | None) -> None:
    with pytest.raises(TopUpError) as raised:
        verify_webhook_signature(b"payload", signature, b"secret")
    assert raised.value.code == "INVALID_WEBHOOK_SIGNATURE"


def test_try_on_estimates_prefer_offering_rate_and_fallback_to_general_rate() -> None:
    estimates = estimate_try_ons(
        100,
        ("BUSINESS", "SHOP", "MIRROR_LITE"),
        {"TRY_ON": 20, "SHOP_TRY_ON": 25},
    )
    assert estimates == (
        {"offering": "BUSINESS", "token_cost": 20, "estimated_try_ons": 5},
        {"offering": "SHOP", "token_cost": 25, "estimated_try_ons": 4},
        {"offering": "MIRROR_LITE", "token_cost": 20, "estimated_try_ons": 5},
    )


def test_try_on_estimate_is_unknown_without_a_published_rate() -> None:
    assert estimate_try_ons(100, ("BUSINESS",), {})[0]["estimated_try_ons"] is None


def test_valid_razorpay_checkout_signature_is_accepted() -> None:
    signature = hmac.new(b"secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
    verify_payment_signature("order_1", "pay_1", signature, b"secret")


@pytest.mark.parametrize(
    "order_id,payment_id,signature",
    [("", "pay_1", "x"), ("order_1", "", "x"), ("order_1", "pay_1", "wrong")],
)
def test_missing_or_invalid_razorpay_signature_is_rejected(
    order_id: str, payment_id: str, signature: str
) -> None:
    with pytest.raises(TopUpError) as raised:
        verify_payment_signature(order_id, payment_id, signature, b"secret")
    assert raised.value.code == "INVALID_PAYMENT_SIGNATURE"
