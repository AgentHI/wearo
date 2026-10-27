import pytest

from apps.api.wearo_api.admin_operations import operation_metrics
from apps.api.wearo_api.tryon_authorization import (
    TryOnAuthorizationError,
    authorize_business_try_on,
)


def test_success_and_failure_metrics_include_both_outcomes() -> None:
    metrics = operation_metrics(successful=3, failed=1, duration_ms=8_000)
    assert metrics == {"success_rate": 75.0, "average_processing_time_ms": 2_000}


def test_empty_operations_have_zero_rate_and_duration() -> None:
    assert operation_metrics(0, 0, 0) == {
        "success_rate": 0.0,
        "average_processing_time_ms": 0,
    }


def test_platform_pause_blocks_only_new_tryon_authorization_and_resume_restores_it() -> None:
    with pytest.raises(TryOnAuthorizationError) as paused:
        authorize_business_try_on("ACTIVE", "ACTIVE", platform_operational=False)
    assert paused.value.code == "PLATFORM_TRYONS_PAUSED"

    authorize_business_try_on("ACTIVE", "ACTIVE", platform_operational=True)


def test_business_type_pause_blocks_matching_tryons() -> None:
    with pytest.raises(TryOnAuthorizationError) as paused:
        authorize_business_try_on("ACTIVE", "ACTIVE", business_type_operational=False)
    assert paused.value.code == "BUSINESS_TYPE_TRYONS_PAUSED"
