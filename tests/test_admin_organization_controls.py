from pathlib import Path

import pytest

from apps.api.wearo_api.admin_organizations import organization_status_after
from apps.api.wearo_api.tryon_authorization import (
    BusinessTryOnStatus,
    TryOnAuthorizationError,
    authorize_business_try_on,
)


def test_pausing_one_organization_blocks_only_that_organization_then_resume_restores_it() -> None:
    first_status = organization_status_after("ACTIVE", "PAUSE")
    second_status: BusinessTryOnStatus = "ACTIVE"

    with pytest.raises(TryOnAuthorizationError, match="paused"):
        authorize_business_try_on(first_status)
    authorize_business_try_on(second_status)

    first_status = organization_status_after(first_status, "RESUME")
    authorize_business_try_on(first_status)
    authorize_business_try_on(second_status)


def test_pause_and_resume_require_valid_current_state() -> None:
    with pytest.raises(ValueError, match="active organization"):
        organization_status_after("PAUSED", "PAUSE")
    with pytest.raises(ValueError, match="paused organization"):
        organization_status_after("ACTIVE", "RESUME")


def test_admin_organization_reports_advertisement_generations_by_store() -> None:
    source = Path("apps/api/wearo_api/admin_organizations.py").read_text()
    assert "store_advertisement_generations" in source
    assert "count(generation.generation_id)" in source
    assert "AS advertisement_generations" in source
    assert "GROUP BY store.store_id" in source
