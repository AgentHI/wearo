from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.wearo_api.browser_sessions import BrowserSession
from apps.api.wearo_api.http_api import ApiContainer, create_app
from apps.api.wearo_api.plan_usage import UsageSnapshot


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


class AllowedBusinessPlatform:
    def __init__(self, tenant_id: UUID) -> None:
        self.tenant_id = tenant_id

    def overview(self, _: UUID, tenant_id: UUID) -> dict[str, object]:
        assert tenant_id == self.tenant_id
        return {}


class RecordingPlanUsage:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    def for_account(self, account_id: UUID, **arguments: object) -> UsageSnapshot:
        self.arguments = {"account_id": account_id, **arguments}
        return UsageSnapshot(
            "LAUNCH",
            1000,
            940,
            60,
            None,
            3,
            3,
            None,
            "TRY_ON",
            20,
            920,
            47,
            2,
            0,
            0,
            0,
            20.0,
            0.1,
            0.004,
        )


def test_business_usage_endpoint_forwards_tenant_action_and_reporting_dates() -> None:
    account_id, principal_id, tenant_id = uuid4(), uuid4(), uuid4()
    usage = RecordingPlanUsage()
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
        business_platform=cast(Any, AllowedBusinessPlatform(tenant_id)),
        plan_usage=cast(Any, usage),
    )

    with TestClient(create_app(container)) as client:
        client.cookies.set("wearo_business_session", "session")
        response = client.get(
            f"/api/v1/business/tenants/{tenant_id}/usage",
            params={
                "action_code": "TRY_ON",
                "date_from": "2026-10-24",
                "date_to": "2026-10-25",
            },
        )

    assert response.status_code == 200
    assert response.json()["average_tokens_per_preview"] == 20.0
    assert usage.arguments == {
        "account_id": account_id,
        "tenant_id": tenant_id,
        "action_code": "TRY_ON",
        "date_from": date(2026, 10, 24),
        "date_to": date(2026, 10, 25),
    }


def test_business_usage_endpoint_rejects_reversed_date_range() -> None:
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
        business_platform=cast(Any, AllowedBusinessPlatform(tenant_id)),
        plan_usage=cast(Any, RecordingPlanUsage()),
    )

    with TestClient(create_app(container)) as client:
        client.cookies.set("wearo_business_session", "session")
        response = client.get(
            f"/api/v1/business/tenants/{tenant_id}/usage",
            params={"date_from": "2026-10-25", "date_to": "2026-10-24"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_DATE_RANGE"
