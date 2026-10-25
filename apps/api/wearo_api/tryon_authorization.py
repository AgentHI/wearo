from __future__ import annotations

from typing import Literal

BusinessTryOnStatus = Literal["ACTIVE", "PAUSED", "CANCELLED"]


class TryOnAuthorizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def authorize_business_try_on(status: BusinessTryOnStatus) -> None:
    """Authorize a new business-owned try-on without affecting read operations."""
    if status == "ACTIVE":
        return
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
    raise TryOnAuthorizationError(
        "TRYON_STATUS_INVALID",
        "The business try-on status is invalid.",
    )
