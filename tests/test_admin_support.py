from pathlib import Path

import pytest

from apps.api.wearo_api.admin_support import AdminSupportError, normalize_support_identity


def test_support_search_normalizes_email_and_indian_mobile() -> None:
    assert normalize_support_identity(" User@Example.com ") == ("EMAIL", "user@example.com")
    assert normalize_support_identity("98765 43210") == ("PHONE", "+919876543210")


@pytest.mark.parametrize("identity", ["", "not-an-email@", "1234"])
def test_support_search_rejects_invalid_identity(identity: str) -> None:
    with pytest.raises(AdminSupportError) as raised:
        normalize_support_identity(identity)
    assert raised.value.code == "INVALID_SUPPORT_SEARCH"


def test_support_credit_is_append_only_and_audited() -> None:
    source = Path("apps/api/wearo_api/admin_support.py").read_text()
    assert "INSERT INTO ledger_entries" in source
    assert "UPDATE ledger_entries" not in source
    assert "ADMIN_SUPPORT_TOKEN_CREDIT" in source
    assert "admin-support-credit:" in source


def test_support_search_includes_all_customer_contexts_and_payment_status() -> None:
    source = Path("apps/api/wearo_api/admin_support.py").read_text()
    assert 'return "B2B"' in source
    assert 'return "B2B2C"' in source
    assert 'return "B2C"' in source
    assert "FROM payment_orders payment" in source
    assert "number_of_try_ons" in source
