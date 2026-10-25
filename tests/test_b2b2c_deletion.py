from pathlib import Path


def test_sponsored_render_attribution_survives_customer_link_anonymization() -> None:
    runtime = Path("apps/api/wearo_api/render_runtime.py").read_text()
    usage = Path("apps/api/wearo_api/plan_usage.py").read_text()
    lifecycle = Path("apps/api/wearo_api/account_lifecycle.py").read_text()

    assert "SET render_job_id = :job" in runtime
    assert "WHERE sponsored.render_job_id = :job" in runtime
    assert "job.job_id = sponsored.render_job_id" in usage
    assert "consumer_account_id = NULL, consumer_principal_id = NULL" in lifecycle
    assert "status = 'EXPIRED'" in lifecycle
    assert "anonymized_at = COALESCE(anonymized_at, :now)" in lifecycle


def test_business_financial_and_aggregate_rows_are_retained() -> None:
    lifecycle = Path("apps/api/wearo_api/account_lifecycle.py").read_text()

    for forbidden_statement in (
        "DELETE FROM business_sponsored_tryons",
        "DELETE FROM billable_usage_records",
        "DELETE FROM ledger_entries",
        "DELETE FROM tenant_aggregate_events",
    ):
        assert forbidden_statement not in lifecycle


def test_b2b2c_schema_allows_identity_links_to_be_cleared() -> None:
    migration = Path(
        "apps/api/migrations/versions/20261025_0040_b2b2c_customer_anonymization.py"
    ).read_text()

    assert migration.count('consumer_account_id", nullable=True') == 2
    assert migration.count('consumer_principal_id", nullable=True') == 2
    assert migration.count('ondelete="SET NULL"') == 3
    assert 'sa.Column("anonymized_at", TIMESTAMP)' in migration
    assert 'sa.Column("render_job_id", UUID)' in migration
