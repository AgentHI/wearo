import pytest

from apps.api.wearo_api.tryon_authorization import (
    TryOnAuthorizationError,
    authorize_business_try_on,
)


def test_active_business_can_start_try_on() -> None:
    authorize_business_try_on("ACTIVE")


def test_paused_business_returns_clear_try_on_error() -> None:
    with pytest.raises(TryOnAuthorizationError) as error:
        authorize_business_try_on("PAUSED")

    assert error.value.code == "TRYONS_PAUSED"
    assert str(error.value) == "Try-ons are paused for this business."


def test_cancelled_business_returns_clear_subscription_error() -> None:
    with pytest.raises(TryOnAuthorizationError) as error:
        authorize_business_try_on("CANCELLED")

    assert error.value.code == "SUBSCRIPTION_CANCELLED"
    assert str(error.value) == "This business subscription is cancelled."
