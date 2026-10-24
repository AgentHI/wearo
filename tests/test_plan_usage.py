from pathlib import Path

import pytest

from apps.api.wearo_api.plan_usage import usage_snapshot


def test_usage_snapshot_explains_before_and_after_billable_action() -> None:
    snapshot = usage_snapshot(
        plan_code="LAUNCH",
        token_balance=105,
        tokens_used=40,
        preview_limit=10,
        previews_used=4,
        action_code="TRY_ON",
        action_cost=20,
        tokens_purchased=200,
        reporting_hours=48,
    )
    assert snapshot.previews_remaining == 6
    assert snapshot.balance_after_action == 85
    assert snapshot.tokens_purchased == 200
    assert snapshot.average_tokens_per_preview == 10
    assert snapshot.estimated_previews == 10
    assert snapshot.average_previews_per_day == 2
    assert snapshot.average_previews_per_hour == pytest.approx(0.0833, rel=0.01)


def test_unlimited_preview_plan_has_no_misleading_remaining_count() -> None:
    snapshot = usage_snapshot(
        plan_code="UNLIMITED",
        token_balance=0,
        tokens_used=0,
        preview_limit=None,
        previews_used=25,
    )
    assert snapshot.previews_remaining is None
    assert snapshot.balance_after_action is None


def test_business_usage_uses_each_table_actual_timestamp_columns() -> None:
    source = Path("apps/api/wearo_api/plan_usage.py").read_text()
    assert "business_sponsored_tryons sponsored" in source
    assert "job.idempotency_key = substring(sponsored.request_key FROM 11)" in source
    assert "OR job.created_at >= :period_start" in source
    assert "OR job.created_at < :period_end" in source
    assert "OR first_seen_at >= :period_start" in source
    assert "OR first_seen_at < :period_end" in source
