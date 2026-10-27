from apps.api.wearo_api.admin_usage_analytics import reconcile_token_activity


def test_purchase_completed_tryons_and_adjustment_reconcile_to_remaining_balance() -> None:
    activity = reconcile_token_activity(
        purchased=1000,
        consumed=60,
        manually_adjusted=25,
    )

    assert activity.purchased == 1000
    assert activity.consumed == 60
    assert activity.manually_adjusted == 25
    assert activity.remaining == 965
