from __future__ import annotations

from typing import Literal

BusinessTryOnStatus = Literal["ACTIVE", "PAUSED", "CANCELLED"]
SubscriptionState = Literal["TRIAL", "ACTIVE", "PAYMENT_DUE", "PAUSED", "CANCELLED", "EXPIRED"]


class TryOnAuthorizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def authorize_business_try_on(
    status: BusinessTryOnStatus,
    subscription_state: SubscriptionState = "ACTIVE",
    *,
    platform_operational: bool = True,
    business_type_operational: bool = True,
) -> None:
    """Authorize a new business-owned try-on without affecting read operations."""
    if not platform_operational:
        raise TryOnAuthorizationError(
            "PLATFORM_TRYONS_PAUSED", "Platform try-ons are temporarily paused."
        )
    if not business_type_operational:
        raise TryOnAuthorizationError(
            "BUSINESS_TYPE_TRYONS_PAUSED", "Try-ons are paused for this business type."
        )
    if status == "PAUSED":
        raise TryOnAuthorizationError(
            "TRYONS_PAUSED",
            "Try-ons are paused for this business.",
        )
    if status == "CANCELLED":
        raise TryOnAuthorizationError(
            "SUBSCRIPTION_CANCELLED",
            "This business subscription is cancelled.",
        )
    if status != "ACTIVE":
        raise TryOnAuthorizationError("TRYON_STATUS_INVALID", "The business status is invalid.")
    if subscription_state in {"ACTIVE", "TRIAL"}:
        return
    messages = {
        "PAYMENT_DUE": ("SUBSCRIPTION_PAYMENT_DUE", "Payment is due for this subscription."),
        "PAUSED": ("SUBSCRIPTION_PAUSED", "This customer paused their subscription."),
        "CANCELLED": ("SUBSCRIPTION_CANCELLED", "This business subscription is cancelled."),
        "EXPIRED": ("SUBSCRIPTION_EXPIRED", "This business subscription has expired."),
    }
    code, message = messages[subscription_state]
    raise TryOnAuthorizationError(code, message)
