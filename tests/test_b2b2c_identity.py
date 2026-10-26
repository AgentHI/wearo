from pathlib import Path


def test_sponsored_sessions_accept_verified_email_or_phone_identity() -> None:
    source = Path("apps/api/wearo_api/sponsored_tryons.py").read_text()

    assert "channel IN ('PHONE', 'EMAIL')" in source
    assert "VERIFIED_IDENTITY_REQUIRED" in source
    assert "normalized_email" in source
    assert "ON CONFLICT (tenant_id, consumer_principal_id)" in source
    assert "if mobile is None:" in source
    assert "SELECT default_try_on_limit" in source
    assert ":mobile IS NOT NULL" not in source


def test_sponsored_consumption_remains_charged_to_business_account() -> None:
    source = Path("apps/api/wearo_api/sponsored_tryons.py").read_text()

    assert '"account": session["business_account_id"]' in source
    assert "INSERT INTO ledger_entries" in source
    assert "INSERT INTO billable_usage_records" in source
    assert "INSERT INTO business_sponsored_tryons" in source
