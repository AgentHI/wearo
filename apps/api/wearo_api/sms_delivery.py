from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import boto3
from botocore.config import Config

from .email_otp import AuthRealm


class SmsVoiceV2Client(Protocol):
    def send_text_message(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AwsSmsSettings:
    region: str
    origination_identity: str
    configuration_set: str = ""
    entity_id: str = ""
    template_id: str = ""
    message_template: str = "Your Wearo OTP is {code}. Do not share it with anyone."

    def __post_init__(self) -> None:
        if not self.region or not self.origination_identity:
            raise ValueError("AWS SMS region and origination identity are required")
        if bool(self.entity_id) != bool(self.template_id):
            raise ValueError("AWS SMS entity ID and template ID must be configured together")
        try:
            rendered = self.message_template.format(code="123456")
        except (KeyError, ValueError) as exc:
            raise ValueError(
                "AWS SMS message template may only use the {code} placeholder"
            ) from exc
        if "123456" not in rendered:
            raise ValueError("AWS SMS message template must contain the {code} placeholder")


class AwsSmsDeliveryProvider:
    """Deliver transactional OTP messages with AWS End User Messaging SMS."""

    def __init__(
        self, settings: AwsSmsSettings, *, client: SmsVoiceV2Client | None = None
    ) -> None:
        self.settings = settings
        self.client = client or boto3.client(
            "pinpoint-sms-voice-v2",
            region_name=settings.region,
            config=Config(
                retries={"total_max_attempts": 3, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=10,
            ),
        )

    def send_sign_in_code(
        self, *, to_mobile: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None:
        request: dict[str, Any] = {
            "DestinationPhoneNumber": to_mobile,
            "OriginationIdentity": self.settings.origination_identity,
            "MessageBody": self.settings.message_template.format(code=code),
            "MessageType": "TRANSACTIONAL",
            "TimeToLive": max(
                1, int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds())
            ),
            "Context": {"purpose": "OTP", "realm": realm},
        }
        if self.settings.configuration_set:
            request["ConfigurationSetName"] = self.settings.configuration_set
        if self.settings.entity_id:
            request["DestinationCountryParameters"] = {
                "IN_ENTITY_ID": self.settings.entity_id,
                "IN_TEMPLATE_ID": self.settings.template_id,
            }
        self.client.send_text_message(**request)


class HttpSmsDeliveryProvider:
    """Legacy provider-neutral SMS adapter configured through environment secrets."""

    def __init__(self, endpoint: str, api_key: str, sender: str) -> None:
        import requests

        if not endpoint or not api_key or not sender:
            raise ValueError("SMS endpoint, API key, and sender are required")
        self.endpoint = endpoint
        self.api_key = api_key
        self.sender = sender
        self._requests = requests

    def send_sign_in_code(
        self, *, to_mobile: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None:
        response = self._requests.post(
            self.endpoint,
            json={
                "to": to_mobile,
                "from": self.sender,
                "message": (
                    f"Your Wearo sign-in code is {code}. "
                    f"It expires at {expires_at.isoformat()}."
                ),
                "purpose": realm,
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        response.raise_for_status()
