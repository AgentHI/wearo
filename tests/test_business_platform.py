from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from apps.api.wearo_api.business_platform import (
    ACTION_EXPLANATIONS,
    BusinessPlatformError,
    PostgresBusinessPlatform,
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


def test_owner_operating_profile_update_is_immediate_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    current_result = MagicMock()
    current_result.scalar_one_or_none.return_value = "BOUTIQUE"
    connection.execute.side_effect = [current_result, MagicMock(), MagicMock()]
    account_id, principal_id, tenant_id = uuid4(), uuid4(), uuid4()
    monkeypatch.setattr(
        PostgresBusinessPlatform,
        "_require_member",
        staticmethod(lambda *_args, **_kwargs: account_id),
    )

    result = PostgresBusinessPlatform(cast(Engine, engine)).update_operating_profile(
        principal_id,
        tenant_id,
        "JEWELLERY_RETAILER",
        "We now sell jewellery.",
    )

    assert result["operating_profile"] == "JEWELLERY_RETAILER"
    assert connection.execute.call_count == 3
    update_call = connection.execute.call_args_list[1]
    audit_call = connection.execute.call_args_list[2]
    assert "UPDATE business_profiles" in str(update_call.args[0])
    assert update_call.args[1]["profile"] == "JEWELLERY_RETAILER"
    assert "OPERATING_PROFILE_UPDATED" in str(audit_call.args[0])
    assert audit_call.args[1]["before"] == '{"operating_profile": "BOUTIQUE"}'
    assert audit_call.args[1]["after"] == '{"operating_profile": "JEWELLERY_RETAILER"}'


def test_operating_profile_change_request_workflow_is_not_used() -> None:
    source = Path("apps/api/wearo_api/business_platform.py").read_text()
    assert "def request_profile_change" not in source
    assert "OPERATING_PROFILE_CHANGE_REQUESTED" not in source
