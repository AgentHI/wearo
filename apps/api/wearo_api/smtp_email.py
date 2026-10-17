from __future__ import annotations

import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage

from .email_otp import AuthRealm


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    use_tls: bool = True


class SmtpEmailDeliveryProvider:
    """Replaceable SMTP delivery; callers must keep credentials outside source control."""

    def __init__(self, settings: SmtpSettings) -> None:
        if not settings.host or not settings.from_address or settings.port < 1:
            raise ValueError("valid SMTP settings are required")
        self.settings = settings

    def send_sign_in_code(
        self, *, to_email: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None:
        message = EmailMessage()
        message["Subject"] = "Your Wearo sign-in code"
        message["From"] = self.settings.from_address
        message["To"] = to_email
        message.set_content(
            f"Your Wearo sign-in code is {code}. It expires at "
            f"{expires_at.isoformat()}. If you did not request this, ignore this email."
        )
        with smtplib.SMTP(self.settings.host, self.settings.port, timeout=10) as client:
            if self.settings.use_tls:
                client.starttls()
            if self.settings.username:
                client.login(self.settings.username, self.settings.password)
            client.send_message(message)
