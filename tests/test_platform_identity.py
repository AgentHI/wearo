import pytest

from apps.api.wearo_api.platform_identity import PlatformIdentityError, offering_access


def test_consumer_and_business_use_canonical_offering_routes() -> None:
    assert offering_access("SHOP", "CONSUMER").launch_url == "/app/"
    assert offering_access("BUSINESS", "BUSINESS").launch_url == "/business/dashboard"
    assert offering_access("MIRROR_LITE", "BUSINESS").name == "Wearo Mirror"


def test_consumer_cannot_open_business_only_offering() -> None:
    with pytest.raises(PlatformIdentityError) as error:
        offering_access("BUSINESS", "CONSUMER")
    assert error.value.code == "OFFERING_UNAVAILABLE"
