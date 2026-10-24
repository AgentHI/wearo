import pytest

from apps.api.wearo_api.wallet_billing import WalletBillingError, validate_request_key


def test_idempotency_key_is_normalized() -> None:
    assert validate_request_key("  request-123  ") == "request-123"


@pytest.mark.parametrize("key", ["", "short", "x" * 101])
def test_invalid_idempotency_key_is_rejected(key: str) -> None:
    with pytest.raises(WalletBillingError) as error:
        validate_request_key(key)
    assert error.value.code == "INVALID_IDEMPOTENCY_KEY"
