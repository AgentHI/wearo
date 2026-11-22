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


def test_anonymized_customers_are_not_exposed_in_business_search_or_lists() -> None:
    source = Path("apps/api/wearo_api/business_allowances.py").read_text()
    assert source.count("anonymized_at IS NULL") == 3
    assert "job.job_id=sponsored.render_job_id" in source
    assert "FROM account_persons person" in source
    assert "JOIN person_tryon_observations observation" in source
    assert "observation.tenant_id=:tenant" in source
    assert "observation.business_account_id=:account" in source
    assert "bool_or(observation.marketing_eligible)" in source


def test_customer_directory_returns_every_person_seen_for_the_shared_login() -> None:
    source = Path("apps/api/wearo_api/business_allowances.py").read_text()
    assert "jsonb_agg(" in source
    assert "'person_id', visible.person_id" in source
    assert "'store_ids', visible.store_ids" in source
    assert '"persons": persons' in source
    assert "one login can represent several family members" in source
