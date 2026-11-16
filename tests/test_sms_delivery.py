from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.api.wearo_api.sms_delivery import AwsSmsDeliveryProvider, AwsSmsSettings


class RecordingSmsClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def send_text_message(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        return {"MessageId": "message-1"}


def test_aws_sms_sends_transactional_otp_with_india_dlt_parameters() -> None:
    client = RecordingSmsClient()
    provider = AwsSmsDeliveryProvider(
        AwsSmsSettings(
            region="ap-south-1",
            origination_identity="WEAROA",
            configuration_set="wearo-otp",
            entity_id="entity-1",
            template_id="template-1",
        ),
        client=client,
    )

    provider.send_sign_in_code(
        to_mobile="+919876543210",
        code="483920",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        realm="BUSINESS",
    )

    request = client.requests[0]
    assert request["DestinationPhoneNumber"] == "+919876543210"
    assert request["OriginationIdentity"] == "WEAROA"
    assert request["MessageBody"] == "Your Wearo OTP is 483920. Do not share it with anyone."
    assert request["MessageType"] == "TRANSACTIONAL"
    assert request["ConfigurationSetName"] == "wearo-otp"
    assert request["DestinationCountryParameters"] == {
        "IN_ENTITY_ID": "entity-1",
        "IN_TEMPLATE_ID": "template-1",
    }
    assert request["Context"] == {"purpose": "OTP", "realm": "BUSINESS"}
    assert 590 <= request["TimeToLive"] <= 600


def test_aws_sms_omits_optional_route_parameters_when_not_configured() -> None:
    client = RecordingSmsClient()
    provider = AwsSmsDeliveryProvider(
        AwsSmsSettings(region="ap-south-1", origination_identity="pool-id"), client=client
    )
    provider.send_sign_in_code(
        to_mobile="+14155550100",
        code="123456",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        realm="SHOP",
    )
    assert "ConfigurationSetName" not in client.requests[0]
    assert "DestinationCountryParameters" not in client.requests[0]


def test_aws_sms_settings_reject_partial_dlt_or_invalid_template() -> None:
    with pytest.raises(ValueError, match="configured together"):
        AwsSmsSettings("ap-south-1", "WEAROA", entity_id="entity-only")
    with pytest.raises(ValueError, match="must contain"):
        AwsSmsSettings("ap-south-1", "WEAROA", message_template="Your Wearo OTP is missing")
