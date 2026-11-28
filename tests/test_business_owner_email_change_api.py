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


class RecordingBusinessMembership:
    def __init__(self, challenge_id: UUID) -> None:
        self.challenge_id = challenge_id
        self.requested: tuple[UUID, UUID, str] | None = None
        self.confirmed: tuple[UUID, UUID, UUID, str, str] | None = None

    def request_owner_email_change(
        self, principal_id: UUID, tenant_id: UUID, *, new_email: str
    ) -> dict[str, object]:
        self.requested = (principal_id, tenant_id, new_email)
        return {
            "challenge_id": self.challenge_id,
            "expires_at": datetime.now(UTC) + timedelta(minutes=10),
            "current_email": "old@example.com",
            "new_email": new_email,
            "message": "Verification codes were sent to both email addresses.",
        }

    def confirm_owner_email_change(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        challenge_id: UUID,
        current_email_otp: str,
        new_email_otp: str,
    ) -> dict[str, object]:
        self.confirmed = (
            principal_id,
            tenant_id,
            challenge_id,
            current_email_otp,
            new_email_otp,
        )
        return {"email": "new@example.com", "signed_out": True}


def test_owner_email_change_requires_both_codes_and_clears_business_cookie() -> None:
    account_id, principal_id, tenant_id, challenge_id = uuid4(), uuid4(), uuid4(), uuid4()
    membership = RecordingBusinessMembership(challenge_id)
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
        business_membership=cast(Any, membership),
        secure_cookie=False,
    )

    with TestClient(create_app(container)) as client:
        client.cookies.set("wearo_business_session", "session")
        requested = client.post(
            f"/api/v1/business/tenants/{tenant_id}/owner-email-change/request",
            headers={"X-CSRF-Token": "csrf"},
            json={"new_email": "new@example.com"},
        )
        confirmed = client.post(
            f"/api/v1/business/tenants/{tenant_id}/owner-email-change/confirm",
            headers={"X-CSRF-Token": "csrf"},
            json={
                "challenge_id": str(challenge_id),
                "current_email_otp": "123456",
                "new_email_otp": "654321",
            },
        )

    assert requested.status_code == 200
    assert confirmed.status_code == 200
    assert "wearo_business_session=" in confirmed.headers["set-cookie"]
    assert "Max-Age=0" in confirmed.headers["set-cookie"]
    assert confirmed.json() == {"email": "new@example.com", "signed_out": True}
    assert membership.requested == (principal_id, tenant_id, "new@example.com")
    assert membership.confirmed == (
        principal_id,
        tenant_id,
        challenge_id,
        "123456",
        "654321",
    )


def test_legacy_owner_contact_endpoint_cannot_bypass_dual_email_verification() -> None:
    account_id, principal_id, tenant_id = uuid4(), uuid4(), uuid4()
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
        business_membership=cast(Any, RecordingBusinessMembership(uuid4())),
        secure_cookie=False,
    )

    with TestClient(create_app(container)) as client:
        client.cookies.set("wearo_business_session", "session")
        response = client.put(
            f"/api/v1/business/tenants/{tenant_id}/owner-contacts",
            headers={"X-CSRF-Token": "csrf"},
            json={
                "channel": "email",
                "value": "new@example.com",
                "otp": "123456",
                "reason": "Change admin",
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "DUAL_VERIFICATION_REQUIRED"
