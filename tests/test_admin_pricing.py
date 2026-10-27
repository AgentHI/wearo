from apps.api.wearo_api.admin_pricing import PricingSnapshot, effective_purchase


def test_new_pricing_does_not_change_existing_purchase_amount() -> None:
    history = (
        PricingSnapshot("v1", 100_00),
        PricingSnapshot("v2", 125_00),
    )

    completed_purchase = effective_purchase(history, "v1")
    new_purchase = effective_purchase(history, "v2")

    assert completed_purchase.amount_minor == 100_00
    assert new_purchase.amount_minor == 125_00
