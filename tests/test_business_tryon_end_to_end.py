from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.wearo_api.beta_profile import PersonProfile
from apps.api.wearo_api.browser_sessions import (
    BrowserSession,
    SessionAuthenticationError,
)
from apps.api.wearo_api.http_api import ApiContainer, create_app
from apps.api.wearo_api.render_runtime import DurableRenderJob
from apps.api.wearo_api.tryon_authorization import (
    BusinessTryOnStatus,
    authorize_business_try_on,
)


class ConsumerSessions:
    cookie = "business-customer-session"
    csrf = "business-customer-csrf"

    def __init__(self, account_id: UUID, principal_id: UUID) -> None:
        now = datetime.now(UTC)
        self.session = BrowserSession(
            uuid4(),
            account_id,
            principal_id,
            "SHOP",
            b"token-hash",
            b"csrf-hash",
            now,
            now + timedelta(hours=1),
            None,
        )

    def authenticate(
        self,
        token: str,
        *,
        expected_realm: str,
        csrf_token: str | None = None,
        mutation: bool = False,
        **_: object,
    ) -> BrowserSession:
        if (
            token != self.cookie
            or expected_realm != "SHOP"
            or (mutation and csrf_token != self.csrf)
        ):
            raise SessionAuthenticationError("invalid session")
        return self.session


class ExistingProfile:
    def __init__(self, profile: PersonProfile) -> None:
        self.profile = profile

    def require(self, account_id: UUID) -> PersonProfile:
        assert account_id == self.profile.account_id
        return self.profile


class StatusAwareRenders:
    def __init__(self, status: BusinessTryOnStatus) -> None:
        self.status = status
        self.create_calls = 0

    def create_job(
        self,
        *,
        quote_id: UUID,
        account_id: UUID,
        principal_id: UUID,
        idempotency_key: str,
    ) -> DurableRenderJob:
        self.create_calls += 1
        authorize_business_try_on(self.status)
        return DurableRenderJob(
            uuid4(),
            quote_id,
            account_id,
            principal_id,
            "PENDING",
            uuid4(),
            uuid4(),
            None,
            None,
            None,
        )

    def list_gallery(self, account_id: UUID) -> tuple[()]:
        return ()

    def list_queue_activity(self, account_id: UUID) -> tuple[()]:
        return ()


def api_client(status: BusinessTryOnStatus) -> tuple[TestClient, StatusAwareRenders]:
    account_id, principal_id = uuid4(), uuid4()
    renders = StatusAwareRenders(status)
    profile = PersonProfile(
        uuid4(),
        account_id,
        principal_id,
        uuid4(),
        uuid4(),
        None,
        None,
        "ACTIVE",
        None,
    )
    unavailable = cast(Any, None)
    container = ApiContainer(
        engine=unavailable,
        otp=unavailable,
        sessions=cast(Any, ConsumerSessions(account_id, principal_id)),
        media=unavailable,
        consents=unavailable,
        profiles=cast(Any, ExistingProfile(profile)),
        quota=unavailable,
        renders=cast(Any, renders),
        secure_cookie=False,
    )
    client = TestClient(create_app(container))
    client.cookies.set("wearo_consumer_session", ConsumerSessions.cookie)
    return client, renders


@pytest.mark.parametrize(
    ("status", "expected_http", "expected_code"),
    (
        ("ACTIVE", 202, None),
        ("PAUSED", 422, "TRYONS_PAUSED"),
        ("CANCELLED", 422, "SUBSCRIPTION_CANCELLED"),
    ),
)
def test_direct_render_endpoint_enforces_business_status(
    status: BusinessTryOnStatus,
    expected_http: int,
    expected_code: str | None,
) -> None:
    client, renders = api_client(status)
    with client:
        response = client.post(
            "/api/v1/renders",
            headers={
                "X-CSRF-Token": ConsumerSessions.csrf,
                "Idempotency-Key": f"direct-{status.casefold()}",
            },
            json={"quote_id": str(uuid4())},
        )

    assert response.status_code == expected_http
    assert renders.create_calls == 1
    if expected_code is None:
        assert response.json()["status"] == "QUEUED"
    else:
        assert response.json()["code"] == expected_code


@pytest.mark.parametrize("status", ("PAUSED", "CANCELLED"))
def test_blocked_business_status_keeps_profile_and_history_reads_available(
    status: BusinessTryOnStatus,
) -> None:
    client, renders = api_client(status)
    with client:
        profile = client.get("/api/v1/me/person-profile")
        history = client.get("/api/v1/renders")

    assert profile.status_code == 200
    assert profile.json()["status"] == "ACTIVE"
    assert history.status_code == 200
    assert history.json()["items"] == []
    assert renders.create_calls == 0
