import pytest

from apps.api.wearo_api.business_platform import (
    ACTION_EXPLANATIONS,
    BusinessPlatformError,
    estimated_actions,
    recommendation_for,
)


def test_operating_profile_drives_catalog_and_offering_recommendations() -> None:
    boutique = recommendation_for("BOUTIQUE")
    jewellery = recommendation_for("JEWELLERY_RETAILER")
    assert boutique.catalog_label == "Designs"
    assert boutique.eligible_offerings == ("BUSINESS",)
    assert jewellery.catalog_label == "Jewellery"
    assert jewellery.eligible_offerings == ()


def test_estimated_actions_uses_published_per_action_rate() -> None:
    assert estimated_actions(105, 20) == 5


def test_schedule_explains_every_required_action_kind() -> None:
    assert set(ACTION_EXPLANATIONS) == {"TRY_ON", "IMAGE_VARIANT", "PREVIEW_3D", "OTHER"}
    assert all("token" not in text.casefold() for text in ACTION_EXPLANATIONS.values())


@pytest.mark.parametrize(("tokens", "cost"), [(-1, 10), (10, 0)])
def test_invalid_estimate_is_rejected(tokens: int, cost: int) -> None:
    with pytest.raises(BusinessPlatformError, match="invalid"):
        estimated_actions(tokens, cost)
