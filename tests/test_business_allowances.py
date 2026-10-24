import pytest

from apps.api.wearo_api.business_allowances import BusinessAllowanceError, normalize_mobile


def test_allowance_mobile_is_normalized_for_exact_search() -> None:
    assert normalize_mobile("+91 (98765) 43210") == "+919876543210"


@pytest.mark.parametrize("value", ["", "98765", "owner@example.com"])
def test_allowance_search_rejects_non_mobile_identifiers(value: str) -> None:
    with pytest.raises(BusinessAllowanceError):
        normalize_mobile(value)
