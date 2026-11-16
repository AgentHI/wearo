import pytest

from apps.api.wearo_api.retail_tryon_pricing import (
    RetailTryOnPricingError,
    package_values,
    tokens_for_price_minor,
)


def test_retail_tryon_price_converts_three_rupees_to_fifteen_tokens() -> None:
    assert tokens_for_price_minor(300) == 15


def test_retail_tryon_price_requires_twenty_paise_increments() -> None:
    with pytest.raises(RetailTryOnPricingError):
        tokens_for_price_minor(310)


def test_package_values_use_amount_and_current_tryon_token_cost() -> None:
    assert package_values(10_000, 15, 1800) == {
        "total_tokens": 500,
        "number_of_tryons": 33,
        "tax_minor": 1800,
        "final_amount_minor": 11800,
    }
