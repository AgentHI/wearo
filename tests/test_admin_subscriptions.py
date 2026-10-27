import pytest

from apps.api.wearo_api.admin_subscriptions import subscription_state_after
from apps.api.wearo_api.tryon_authorization import (
    SubscriptionState,
    TryOnAuthorizationError,
    authorize_business_try_on,
)


def test_customer_moves_through_lifecycle_with_expected_tryon_eligibility() -> None:
    state: SubscriptionState = "TRIAL"
    authorize_business_try_on("ACTIVE", state)

    state = subscription_state_after(state, "ACTIVATE")
    authorize_business_try_on("ACTIVE", state)

    state = subscription_state_after(state, "MARK_PAYMENT_DUE")
    with pytest.raises(TryOnAuthorizationError, match="Payment is due"):
        authorize_business_try_on("ACTIVE", state)

    state = subscription_state_after(state, "PAUSE")
    with pytest.raises(TryOnAuthorizationError, match="customer paused"):
        authorize_business_try_on("ACTIVE", state)

    state = subscription_state_after(state, "ACTIVATE")
    authorize_business_try_on("ACTIVE", state)


def test_admin_pause_is_distinct_from_customer_subscription_pause() -> None:
    with pytest.raises(TryOnAuthorizationError, match="paused for this business"):
        authorize_business_try_on("PAUSED", "ACTIVE")
    with pytest.raises(TryOnAuthorizationError, match="customer paused"):
        authorize_business_try_on("ACTIVE", "PAUSED")
