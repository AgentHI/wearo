from datetime import UTC, datetime, timedelta
from pathlib import Path

from apps.api.wearo_api.admin_billing import payment_status


def test_payment_statuses_include_paid_pending_failed_and_overdue() -> None:
    now = datetime(2026, 10, 26, tzinfo=UTC)
    assert payment_status("CONFIRMED", now, 7, now) == "PAID"
    assert payment_status("FAILED", now, 7, now) == "FAILED"
    assert payment_status("PENDING", now, 7, now) == "PENDING"
    assert payment_status("PENDING", now - timedelta(days=8), 7, now) == "OVERDUE"


def test_duplicate_confirmation_guard_precedes_credit_and_subscription_update() -> None:
    source = Path("apps/api/wearo_api/topups.py").read_text(encoding="utf-8")
    guard = source.index('if order["state"] == "CONFIRMED"')
    credit = source.index("INSERT INTO ledger_entries", guard)
    subscription = source.index("UPDATE business_subscriptions", guard)
    assert guard < credit < subscription
