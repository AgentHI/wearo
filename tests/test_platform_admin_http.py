from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.wearo_api.http_api import ApiContainer, create_app
from apps.api.wearo_api.platform_admin_auth import PlatformAdminAuth


class FakeAdminOrganizations:
    def __init__(self) -> None:
        self.tenant_id = uuid4()

    def list(self, **_: object) -> dict[str, Any]:
        return {
            "summary": {"total": 1, "active": 1, "paused": 0},
            "organizations": [
                {
                    "tenant_id": self.tenant_id,
                    "organization_name": "Newly Registered Boutique",
                    "business_type": "BOUTIQUE",
                    "onboarding_date": "2026-10-26T12:00:00Z",
                    "subscription_status": "UNASSIGNED",
                    "operational_status": "ACTIVE",
                }
            ],
        }

    def get(self, tenant_id: object) -> dict[str, object]:
        assert tenant_id == self.tenant_id
        organizations = cast(list[dict[str, object]], self.list()["organizations"])
        return organizations[0]

    def change_status(self, tenant_id: object, action: str, reason: str) -> dict[str, str]:
        assert tenant_id == self.tenant_id and reason
        return {"operational_status": "PAUSED" if action == "PAUSE" else "ACTIVE"}

    def adjust_tokens(self, tenant_id: object, amount: int, reason: str) -> dict[str, int]:
        assert tenant_id == self.tenant_id and reason
        return {"available_tokens": 1000 + amount, "adjustment": amount}


class FakeAdminDashboard:
    def metrics(self, **_: object) -> dict[str, int | float]:
        return {
            "total_organizations": 2,
            "active_organizations": 2,
            "total_registered_consumers": 3,
            "total_try_ons": 5,
            "successful_try_ons": 4,
            "failed_try_ons": 1,
            "total_tokens_consumed": 80,
            "average_try_ons_per_organization": 2.5,
        }


class FakeAdminUsageAnalytics:
    def organizations(self, **_: object) -> dict[str, object]:
        return {
            "organizations": [
                {
                    "organization_name": "One",
                    "total_try_ons": 2,
                    "successful_try_ons": 1,
                    "failed_try_ons": 1,
                    "tokens_purchased": 100,
                    "tokens_consumed": 20,
                    "manually_adjusted": 5,
                    "remaining_tokens": 85,
                }
            ],
            "most_active": [],
        }

    def history(self, tenant_id: object, **_: object) -> dict[str, object]:
        return {"tenant_id": tenant_id, "items": []}


class FakeAdminCustomers:
    def list(self, **_: object) -> dict[str, object]:
        return {
            "summary": {
                "total": 2,
                "active": 1,
                "trial": 1,
                "pending_payment": 0,
                "paused": 1,
                "cancelled": 0,
                "expired": 0,
            },
            "customers": [],
        }


class FakeAdminSubscriptions:
    def get(self, tenant_id: object) -> dict[str, object]:
        return {"tenant_id": tenant_id, "plan_code": "TRIAL", "state": "TRIAL"}

    def transition(self, tenant_id: object, action: str, reason: str) -> dict[str, object]:
        assert reason
        return {"tenant_id": tenant_id, "plan_code": "GROWTH", "state": "ACTIVE"}

    def assign_plan(
        self, tenant_id: object, plan: str, next_at: object, reason: str
    ) -> dict[str, object]:
        assert plan and reason
        return {"tenant_id": tenant_id, "plan_code": plan, "state": "ACTIVE"}

    def extend_trial(self, tenant_id: object, days: int, reason: str) -> dict[str, object]:
        assert days and reason
        return {"tenant_id": tenant_id, "plan_code": "TRIAL", "state": "TRIAL"}


class FakeAdminPricing:
    def current(self) -> dict[str, object]:
        return {"settings": [], "token_packages": []}

    def publish_settings(self, values: dict[str, object], reason: str) -> dict[str, object]:
        assert values and reason
        return {"pricing_id": uuid4()}

    def publish_package(self, values: dict[str, object], reason: str) -> dict[str, object]:
        assert values and reason
        return {"pack_id": uuid4()}


class FakeAdminRevenue:
    def metrics(self, **values: object) -> dict[str, object]:
        assert values["date_from"] and values["date_to"]
        return {
            "total_revenue_minor": 15000,
            "monthly_subscription_revenue_minor": 10000,
            "token_purchase_revenue_minor": 5000,
            "pending_collections_minor": 2500,
            "estimated_ai_generation_cost_minor": 3000,
            "actual_recorded_ai_cost_minor": 2800,
            "estimated_gross_margin_minor": 12000,
            "estimated_gross_margin_percent": 80.0,
        }


class FakeAdminOperations:
    def list(self, **_: object) -> dict[str, object]:
        return {
            "summary": {
                "total_requests": 2,
                "successful_requests": 1,
                "failed_requests": 1,
                "success_rate": 50.0,
                "average_processing_time_ms": 1500,
            },
            "failure_reasons": [{"reason": "PROVIDER_ERROR", "count": 1}],
            "requests": [{"job_id": str(uuid4()), "status": "DELIVERED"}],
        }

    def detail(self, job_id: object) -> dict[str, object]:
        return {"job_id": job_id, "status": "DELIVERED", "images_exposed": False}


class FakeAdminAudit:
    def list(self, **values: object) -> dict[str, object]:
        assert values["search"] == "pause"
        return {
            "count": 1,
            "editable": False,
            "events": [
                {
                    "action": "ADMIN_TRYONS_PAUSE",
                    "actor_name": "Wearo Super Admin",
                    "reason": "Maintenance",
                }
            ],
        }


def admin_client(
    organizations: object | None = None,
    dashboard: object | None = None,
    usage_analytics: object | None = None,
    customers: object | None = None,
    subscriptions: object | None = None,
    pricing: object | None = None,
    revenue: object | None = None,
    operations: object | None = None,
    audit: object | None = None,
) -> TestClient:
    unused = cast(Any, object())
    container = ApiContainer(
        engine=unused,
        otp=unused,
        sessions=unused,
        media=unused,
        consents=unused,
        profiles=unused,
        quota=unused,
        renders=unused,
        platform_admin_auth=PlatformAdminAuth("admin@wearo.ai", "correct-secret"),
        admin_organizations=cast(Any, organizations),
        admin_dashboard=cast(Any, dashboard),
        admin_usage_analytics=cast(Any, usage_analytics),
        admin_customers=cast(Any, customers),
        admin_subscriptions=cast(Any, subscriptions),
        admin_pricing=cast(Any, pricing),
        admin_revenue=cast(Any, revenue),
        admin_operations=cast(Any, operations),
        admin_audit=cast(Any, audit),
        secure_cookie=True,
    )
    return TestClient(create_app(container), base_url="https://wearo.ai")


def test_admin_revenue_requires_authentication_and_returns_reconciled_metrics() -> None:
    with admin_client(revenue=FakeAdminRevenue()) as client:
        path = "/api/v1/admin/revenue?date_from=2026-10-01&date_to=2026-10-31"
        assert client.get(path).status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        result = client.get(path)
        assert result.status_code == 200
        assert result.json()["total_revenue_minor"] == 15000
        assert result.json()["estimated_gross_margin_minor"] == 12000


def test_tryon_operations_show_success_and_failure_without_images() -> None:
    with admin_client(operations=FakeAdminOperations()) as client:
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        result = client.get(
            "/api/v1/admin/operations/try-ons?date_from=2026-10-01&date_to=2026-10-31"
        )
        assert result.status_code == 200
        assert result.json()["summary"]["successful_requests"] == 1
        assert result.json()["summary"]["failed_requests"] == 1

        job_id = uuid4()
        detail = client.get(f"/api/v1/admin/operations/try-ons/{job_id}")
        assert detail.json()["images_exposed"] is False


def test_admin_audit_history_is_authenticated_and_read_only() -> None:
    with admin_client(audit=FakeAdminAudit()) as client:
        assert client.get("/api/v1/admin/audit-history?search=pause").status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        result = client.get("/api/v1/admin/audit-history?search=pause")
        assert result.status_code == 200
        assert result.json()["editable"] is False
        assert result.json()["events"][0]["reason"] == "Maintenance"
        assert client.delete("/api/v1/admin/audit-history").status_code == 405


def test_admin_login_session_and_logout_flow() -> None:
    with admin_client() as client:
        assert client.get("/api/v1/admin/session").status_code == 401
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        assert response.status_code == 200
        assert response.json() == {"redirect_to": "/admin/dashboard"}
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=strict" in cookie
        assert "correct-secret" not in response.text
        assert client.get("/api/v1/admin/session").json() == {"authenticated": True}

        assert client.post("/api/v1/admin/logout").status_code == 204
        assert client.get("/api/v1/admin/session").status_code == 401


def test_wrong_and_non_admin_credentials_receive_same_generic_error() -> None:
    with admin_client() as client:
        wrong_password = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "wrong"},
        )
        other_realm = client.post(
            "/api/v1/admin/login",
            json={"email": "business@example.com", "password": "some-password"},
        )
        assert wrong_password.status_code == other_realm.status_code == 401
        assert wrong_password.json()["message"] == other_realm.json()["message"]


def test_business_consumer_and_agent_cookies_cannot_authenticate_admin() -> None:
    with admin_client() as client:
        for cookie_name in (
            "wearo_business_session",
            "wearo_consumer_session",
            "wearo_agent_session",
        ):
            client.cookies.clear()
            client.cookies.set(cookie_name, "a-valid-looking-but-unrelated-token")
            assert client.get("/api/v1/admin/session").status_code == 401


def test_newly_registered_business_appears_in_admin_organization_list_and_details() -> None:
    organizations = FakeAdminOrganizations()
    with admin_client(organizations) as client:
        assert client.get("/api/v1/admin/organizations").status_code == 401
        login = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        assert login.status_code == 200

        listing = client.get("/api/v1/admin/organizations")
        assert listing.status_code == 200
        assert listing.json()["summary"] == {"total": 1, "active": 1, "paused": 0}
        assert listing.json()["organizations"][0]["organization_name"] == (
            "Newly Registered Boutique"
        )
        detail = client.get(f"/api/v1/admin/organizations/{organizations.tenant_id}")
        assert detail.status_code == 200
        assert detail.json()["business_type"] == "BOUTIQUE"
        paused = client.post(
            f"/api/v1/admin/organizations/{organizations.tenant_id}/status",
            json={"action": "PAUSE", "reason": "Operational review"},
        )
        assert paused.json() == {"operational_status": "PAUSED"}
        adjustment = client.post(
            f"/api/v1/admin/organizations/{organizations.tenant_id}/token-adjustments",
            json={"amount": 25, "reason": "Service recovery credit"},
        )
        assert adjustment.json() == {"available_tokens": 1025, "adjustment": 25}


def test_platform_dashboard_requires_admin_and_returns_consolidated_metrics() -> None:
    with admin_client(dashboard=FakeAdminDashboard()) as client:
        url = "/api/v1/admin/dashboard?date_from=2026-10-01&date_to=2026-10-26"
        assert client.get(url).status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        response = client.get(url + "&business_type=BOUTIQUE")
        assert response.status_code == 200
        assert response.json()["total_try_ons"] == 5
        assert response.json()["total_tokens_consumed"] == 80


def test_admin_usage_analytics_and_history_are_protected() -> None:
    tenant_id = uuid4()
    with admin_client(usage_analytics=FakeAdminUsageAnalytics()) as client:
        query = "?date_from=2026-10-01&date_to=2026-10-26"
        assert client.get("/api/v1/admin/usage/organizations" + query).status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        listing = client.get("/api/v1/admin/usage/organizations" + query)
        assert listing.status_code == 200
        assert listing.json()["organizations"][0]["remaining_tokens"] == 85
        history = client.get(f"/api/v1/admin/usage/organizations/{tenant_id}{query}")
        assert history.status_code == 200


def test_customer_subscription_dashboard_is_admin_only() -> None:
    with admin_client(customers=FakeAdminCustomers()) as client:
        assert client.get("/api/v1/admin/customers").status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        response = client.get("/api/v1/admin/customers?status=PAUSED")
        assert response.status_code == 200
        assert response.json()["summary"]["paused"] == 1


def test_subscription_lifecycle_endpoints_require_admin_and_apply_changes() -> None:
    tenant_id = uuid4()
    with admin_client(subscriptions=FakeAdminSubscriptions()) as client:
        endpoint = f"/api/v1/admin/subscriptions/{tenant_id}"
        assert client.get(endpoint).status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        assert client.get(endpoint).json()["state"] == "TRIAL"
        activated = client.post(
            endpoint + "/transitions",
            json={"action": "ACTIVATE", "reason": "Payment confirmed"},
        )
        assert activated.json()["state"] == "ACTIVE"


def test_platform_pricing_settings_are_admin_only_and_versioned() -> None:
    with admin_client(pricing=FakeAdminPricing()) as client:
        assert client.get("/api/v1/admin/pricing").status_code == 401
        client.post(
            "/api/v1/admin/login",
            json={"email": "admin@wearo.ai", "password": "correct-secret"},
        )
        body = {
            "plan_code": "GROWTH",
            "business_type": "BOUTIQUE",
            "monthly_fee_minor": 100000,
            "try_on_token_cost": 20,
            "free_trial_tokens": 100,
            "trial_duration_days": 14,
            "payment_grace_days": 7,
            "gst_basis_points": 1800,
            "reason": "Publish India MVP pricing",
        }
        assert client.post("/api/v1/admin/pricing/settings", json=body).status_code == 201
