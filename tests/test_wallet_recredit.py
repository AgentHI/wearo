import pytest

from apps.api.wearo_api.wallet_billing import automatic_recredit_reason


@pytest.mark.parametrize(
    ("outcome", "started", "expected"),
    [
        ("FAILED", True, "FAILED"),
        ("CANCELLED", False, "CANCELLED_BEFORE_PROCESSING"),
        ("NON_DELIVERED", True, "NON_DELIVERED"),
        ("CANCELLED", True, None),
    ],
)
def test_automatic_recredit_policy(outcome: str, started: bool, expected: str | None) -> None:
    assert (
        automatic_recredit_reason(outcome, processing_started=started, delivered=False) == expected
    )


def test_delivered_action_is_never_automatically_recredited() -> None:
    assert automatic_recredit_reason("FAILED", processing_started=True, delivered=True) is None
