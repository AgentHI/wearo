from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.wearo_api.browser_sessions import BrowserSession
from apps.api.wearo_api.http_api import ApiContainer, create_app


class StaticBusinessSessions:
    def __init__(self, account_id: UUID, principal_id: UUID) -> None:
        self.account_id = account_id
        self.principal_id = principal_id

    def authenticate(self, _: str, **__: object) -> BrowserSession:
        now = datetime.now(UTC)
        return BrowserSession(
            uuid4(),
            self.account_id,
            self.principal_id,
            "BUSINESS",
            b"token",
            b"csrf",
            now,
            now + timedelta(hours=1),
            None,
        )


class RecordingBusinessPlatform:
    def __init__(self) -> None:
        self.arguments: tuple[UUID, UUID, str, str] | None = None

    def update_operating_profile(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        operating_profile: str,
        reason: str,
    ) -> dict[str, object]:
        self.arguments = (principal_id, tenant_id, operating_profile, reason)
        return {
            "operating_profile": operating_profile,
            "recommendation": {
                "catalog_label": "Jewellery",
                "eligible_offerings": (),
                "required_catalog_fields": ("title", "price", "material", "dimensions"),
            },
        }


def test_business_owner_can_update_operating_profile_without_requesting_approval() -> None:
    account_id, principal_id, tenant_id = uuid4(), uuid4(), uuid4()
    platform = RecordingBusinessPlatform()
    unavailable = cast(Any, None)
    container = ApiContainer(
        engine=unavailable,
        otp=unavailable,
        sessions=cast(Any, StaticBusinessSessions(account_id, principal_id)),
        media=unavailable,
        consents=unavailable,
        profiles=unavailable,
        quota=unavailable,
        renders=unavailable,
        business_platform=cast(Any, platform),
        secure_cookie=False,
    )

    with TestClient(create_app(container)) as client:
        client.cookies.set("wearo_business_session", "session")
        response = client.put(
            f"/api/v1/business/tenants/{tenant_id}/operating-profile",
            headers={"X-CSRF-Token": "csrf"},
            json={
                "operating_profile": "JEWELLERY_RETAILER",
                "reason": "We now sell jewellery.",
            },
        )

    assert response.status_code == 200
    assert response.json()["operating_profile"] == "JEWELLERY_RETAILER"
    assert platform.arguments == (
        principal_id,
        tenant_id,
        "JEWELLERY_RETAILER",
        "We now sell jewellery.",
    )
