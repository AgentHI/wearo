from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.wearo_api.contact_enquiries import (
    ContactEnquiryError,
    PostgresContactEnquiries,
)
from apps.api.wearo_api.http_api import ApiContainer, create_app

CONTACT_TOKEN = b"a-browser-visible-contact-token-of-32-bytes"
CONTACT_BODY = {
    "name": "  Priya   Sharma  ",
    "email": "PRIYA@EXAMPLE.COM",
    "mobile": "+91 98765 43210",
    "website_url": "https://example.com",
    "purpose": "BRAND_TRY_ON",
}


class RecordingContactEnquiries:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    def create(self, **arguments: object) -> dict[str, object]:
        self.arguments = arguments
        return {
            "contact_enquiry_id": uuid4(),
            "status": "SUBMITTED",
            "created_at": datetime.now(UTC),
        }


def contact_client(
    service: RecordingContactEnquiries, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setenv("WEARO_CONSUMER_ORIGIN", "https://wearo.ai")
    unavailable = cast(Any, None)
    container = ApiContainer(
        engine=unavailable,
        otp=unavailable,
        sessions=unavailable,
        media=unavailable,
        consents=unavailable,
        profiles=unavailable,
        quota=unavailable,
        renders=unavailable,
        contact_enquiries=cast(Any, service),
        contact_form_token=CONTACT_TOKEN,
    )
    return TestClient(create_app(container), base_url="https://wearo.ai")


def test_contact_api_accepts_valid_business_enquiry(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RecordingContactEnquiries()
    with contact_client(service, monkeypatch) as client:
        response = client.post(
            "/api/v1/public/contact-enquiries",
            json=CONTACT_BODY,
            headers={
                "Origin": "https://wearo.ai",
                "X-Wearo-Contact-Token": CONTACT_TOKEN.decode(),
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "SUBMITTED"
    assert service.arguments["purpose"] == "BRAND_TRY_ON"
    assert service.arguments["website_url"] == "https://example.com"
    assert isinstance(service.arguments["request_id"], str)


def test_contact_api_rejects_missing_or_incorrect_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RecordingContactEnquiries()
    with contact_client(service, monkeypatch) as client:
        response = client.post(
            "/api/v1/public/contact-enquiries",
            json=CONTACT_BODY,
            headers={"Origin": "https://wearo.ai"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CONTACT_TOKEN"
    assert service.arguments == {}


def test_contact_api_rejects_another_browser_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RecordingContactEnquiries()
    with contact_client(service, monkeypatch) as client:
        response = client.post(
            "/api/v1/public/contact-enquiries",
            json=CONTACT_BODY,
            headers={
                "Origin": "https://attacker.example",
                "X-Wearo-Contact-Token": CONTACT_TOKEN.decode(),
            },
        )

    assert response.status_code == 403
    assert response.json()["code"] == "CONTACT_ORIGIN_REJECTED"
    assert service.arguments == {}


def test_contact_api_requires_supported_purpose(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RecordingContactEnquiries()
    with contact_client(service, monkeypatch) as client:
        response = client.post(
            "/api/v1/public/contact-enquiries",
            json={**CONTACT_BODY, "purpose": "PERSONAL_SUPPORT"},
            headers={
                "Origin": "https://wearo.ai",
                "X-Wearo-Contact-Token": CONTACT_TOKEN.decode(),
            },
        )

    assert response.status_code == 422
    assert service.arguments == {}


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"email": "not-an-email"}, "INVALID_CONTACT_EMAIL"),
        ({"mobile": "abc"}, "INVALID_CONTACT_MOBILE"),
        ({"website_url": "javascript:alert(1)"}, "INVALID_CONTACT_WEBSITE"),
    ],
)
def test_contact_repository_rejects_invalid_contact_data_before_database_write(
    overrides: dict[str, str], code: str
) -> None:
    repository = PostgresContactEnquiries(cast(Any, None))
    with pytest.raises(ContactEnquiryError) as error:
        repository.create(
            name=str(overrides.get("name", CONTACT_BODY["name"])),
            email=str(overrides.get("email", CONTACT_BODY["email"])),
            mobile=str(overrides.get("mobile", CONTACT_BODY["mobile"])),
            website_url=str(overrides.get("website_url", CONTACT_BODY["website_url"])),
            purpose="BRAND_TRY_ON",
            request_id="request-1",
        )

    assert error.value.code == code
