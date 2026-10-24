import hashlib
import hmac

import pytest

from apps.api.wearo_api.topups import TopUpError, estimate_try_ons, verify_webhook_signature


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
