from apps.api.wearo_api.admin_revenue import RevenueTotals


def test_revenue_and_estimated_margin_reconcile() -> None:
    totals = RevenueTotals(
        received_minor=150_00,
        subscription_minor=100_00,
        token_minor=50_00,
        pending_minor=25_00,
        estimated_ai_cost_minor=30_00,
        actual_ai_cost_minor=28_00,
    )
    assert totals.subscription_minor + totals.token_minor == totals.received_minor
    assert totals.estimated_gross_margin_minor == 120_00
    assert totals.estimated_gross_margin_percent == 80.0


def test_pending_payments_are_not_received_revenue() -> None:
    totals = RevenueTotals(100_00, 0, 100_00, 40_00, 10_00, 8_00)
    assert totals.received_minor == 100_00
    assert totals.pending_minor == 40_00
    assert totals.estimated_gross_margin_minor == 90_00
