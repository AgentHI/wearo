from pathlib import Path

import pytest

from apps.api.wearo_api.business_allowances import BusinessAllowanceError, normalize_mobile


def test_allowance_mobile_is_normalized_for_exact_search() -> None:
    assert normalize_mobile("+91 (98765) 43210") == "+919876543210"


@pytest.mark.parametrize("value", ["", "98765", "owner@example.com"])
def test_allowance_search_rejects_non_mobile_identifiers(value: str) -> None:
    with pytest.raises(BusinessAllowanceError):
        normalize_mobile(value)


def test_added_allowance_reactivates_current_sponsored_session() -> None:
    source = Path("apps/api/wearo_api/business_allowances.py").read_text()
    assert "UPDATE business_sponsored_sessions session" in source
    assert "session.allowance_limit + :amount" in source
    assert "session.status='EXHAUSTED'" in source
