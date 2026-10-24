from __future__ import annotations

from datetime import datetime

import requests

from .email_otp import AuthRealm


class HttpSmsDeliveryProvider:
    """Small provider-neutral SMS adapter configured entirely through environment secrets."""

    def __init__(self, endpoint: str, api_key: str, sender: str) -> None:
        if not endpoint or not api_key or not sender:
            raise ValueError("SMS endpoint, API key, and sender are required")
        self.endpoint = endpoint
        self.api_key = api_key
        self.sender = sender

    def send_sign_in_code(
        self, *, to_mobile: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None:
        response = requests.post(
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
