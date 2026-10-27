from apps.api.wearo_api.admin_customers import customer_counts, customer_statuses


def test_subscription_status_change_updates_corresponding_customer_count() -> None:
    active = customer_statuses(
        subscription_state="ACTIVE",
        payment_pending=False,
        try_on_status="ACTIVE",
    )
    other = customer_statuses(
        subscription_state="TRIAL",
        payment_pending=True,
        try_on_status="ACTIVE",
    )
    before = customer_counts((active, other))
    assert before == {
        "total": 2,
        "active": 2,
        "trial": 1,
        "pending_payment": 1,
        "paused": 0,
        "cancelled": 0,
        "expired": 0,
    }

    paused = customer_statuses(
        subscription_state="ACTIVE",
        payment_pending=False,
        try_on_status="PAUSED",
    )
    after = customer_counts((paused, other))
    assert after["active"] == 1
    assert after["paused"] == 1
    assert after["total"] == 2


def test_cancelled_and_expired_subscriptions_are_distinct() -> None:
    cancelled = customer_statuses(
        subscription_state="CANCELLED",
        payment_pending=False,
        try_on_status="CANCELLED",
    )
    expired = customer_statuses(
        subscription_state="EXPIRED",
        payment_pending=False,
        try_on_status="ACTIVE",
    )
    counts = customer_counts((cancelled, expired))
    assert counts["cancelled"] == 1
    assert counts["expired"] == 1
