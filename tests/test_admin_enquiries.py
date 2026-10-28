from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from apps.api.wearo_api.admin_enquiries import AdminEnquiryError, PostgresAdminEnquiries
from apps.api.wearo_api.http_api import ApiContainer, create_app
from apps.api.wearo_api.platform_admin_auth import PlatformAdminAuth


class RecordingAdminEnquiries:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    def list(self, **arguments: object) -> dict[str, object]:
        self.arguments = arguments
        return {
            "summary": {"total": 3, "submitted": 2, "in_review": 1, "closed": 0},
            "enquiries": [
                {
                    "contact_enquiry_id": "00000000-0000-0000-0000-000000000001",
                    "name": "Priya Sharma",
                    "email": "priya@example.com",
                    "mobile": "+91 98765 43210",
                    "website_url": "https://example.com",
                    "purpose": "BRAND_TRY_ON",
                    "status": "SUBMITTED",
                    "created_at": "2026-10-28T10:00:00Z",
                }
            ],
        }


def admin_client(enquiries: RecordingAdminEnquiries) -> TestClient:
    unavailable = cast(Any, object())
    return TestClient(
        create_app(
            ApiContainer(
                engine=unavailable,
                otp=unavailable,
                sessions=unavailable,
                media=unavailable,
                consents=unavailable,
                profiles=unavailable,
                quota=unavailable,
                renders=unavailable,
                platform_admin_auth=PlatformAdminAuth("admin@wearo.ai", "correct-secret"),
                admin_enquiries=cast(Any, enquiries),
                secure_cookie=True,
            )
        ),
        base_url="https://wearo.ai",
    )


def test_admin_enquiries_require_super_admin_and_forward_filters() -> None:
    enquiries = RecordingAdminEnquiries()
    with admin_client(enquiries) as client:
        path = "/api/v1/admin/enquiries?search=priya&purpose=BRAND_TRY_ON&status=SUBMITTED"
        assert client.get(path).status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        response = client.get(path)

    assert response.status_code == 200
    assert response.json()["summary"]["submitted"] == 2
    assert response.json()["enquiries"][0]["email"] == "priya@example.com"
    assert enquiries.arguments == {
        "search": "priya",
        "purpose": "BRAND_TRY_ON",
        "status": "SUBMITTED",
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"purpose": "PERSONAL_SUPPORT"}, "purpose"),
        ({"status": "DELETED"}, "status"),
    ],
)
def test_admin_enquiry_repository_rejects_unsupported_filters_before_query(
    arguments: dict[str, str], message: str
) -> None:
    repository = PostgresAdminEnquiries(cast(Any, None))
    with pytest.raises(AdminEnquiryError, match=message):
        repository.list(**arguments)
