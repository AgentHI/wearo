from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import Engine, text

ContactPurpose = Literal[
    "BRAND_TRY_ON",
    "RETAIL_PARTNERSHIP",
    "ENTERPRISE_DEMO",
    "TECHNOLOGY_PARTNERSHIP",
    "PRESS",
    "OTHER",
]

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MOBILE_PATTERN = re.compile(r"^[0-9+() .-]{7,32}$")


class ContactEnquiryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PostgresContactEnquiries:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(
        self,
        *,
        name: str,
        email: str,
        mobile: str,
        website_url: str | None,
        purpose: ContactPurpose,
        request_id: str,
    ) -> dict[str, object]:
        clean_name = " ".join(name.split())
        clean_email = email.strip().casefold()
        clean_mobile = " ".join(mobile.split())
        clean_website = website_url.strip() if website_url else None

        if not clean_name or len(clean_name) > 120:
            raise ContactEnquiryError("INVALID_CONTACT_NAME", "Enter a valid name.")
        if len(clean_email) > 320 or not EMAIL_PATTERN.fullmatch(clean_email):
            raise ContactEnquiryError("INVALID_CONTACT_EMAIL", "Enter a valid business email.")
        if not MOBILE_PATTERN.fullmatch(clean_mobile):
            raise ContactEnquiryError("INVALID_CONTACT_MOBILE", "Enter a valid mobile number.")
        if clean_website:
            parsed = urlparse(clean_website)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ContactEnquiryError(
                    "INVALID_CONTACT_WEBSITE", "Enter a valid HTTP or HTTPS website URL."
                )

        now = datetime.now(UTC)
        enquiry_id = uuid4()
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text("""INSERT INTO contact_enquiries
                    (contact_enquiry_id, name, email, mobile, website_url, purpose,
                     status, request_id, created_at, updated_at)
                    VALUES (:enquiry_id, :name, :email, :mobile, :website, :purpose,
                            'SUBMITTED', :request_id, :now, :now)
                    RETURNING contact_enquiry_id, status, created_at"""),
                    {
                        "enquiry_id": enquiry_id,
                        "name": clean_name,
                        "email": clean_email,
                        "mobile": clean_mobile,
                        "website": clean_website,
                        "purpose": purpose,
                        "request_id": request_id,
                        "now": now,
                    },
                )
                .mappings()
                .one()
            )
        return dict(row)
