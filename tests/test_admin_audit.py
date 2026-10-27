from pathlib import Path


def test_required_admin_actions_write_audit_events() -> None:
    files = [
        "apps/api/wearo_api/admin_subscriptions.py",
        "apps/api/wearo_api/admin_organizations.py",
        "apps/api/wearo_api/admin_pricing.py",
        "apps/api/wearo_api/admin_platform_controls.py",
    ]
    source = "\n".join(Path(file).read_text(encoding="utf-8") for file in files)
    for action in (
        "ADMIN_SUBSCRIPTION_",
        "ADMIN_TOKEN_ADJUSTMENT",
        "ADMIN_PRICING_PUBLISHED",
        "ADMIN_TRYONS_",
    ):
        assert action in source
    assert source.count("INSERT INTO audit_events") >= 4


def test_admin_audit_has_no_mutation_endpoint() -> None:
    source = Path("apps/api/wearo_api/http_api.py").read_text(encoding="utf-8")
    assert '@app.get("/api/v1/admin/audit-history")' in source
    assert '@app.post("/api/v1/admin/audit-history")' not in source
    assert '@app.put("/api/v1/admin/audit-history")' not in source
    assert '@app.delete("/api/v1/admin/audit-history")' not in source
