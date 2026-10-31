from typing import Any, cast

import pytest

from apps.api.wearo_api.admin_realtime import AdminRealtimeError, PostgresAdminRealtime


class RealtimeForTest(PostgresAdminRealtime):
    def __init__(self) -> None:
        self.now = 10.0
        self.loads = 0
        super().__init__(cast(Any, object()), cache_seconds=2, clock=lambda: self.now)

    def _load(self, window_minutes: int) -> dict[str, object]:
        self.loads += 1
        return {"window_minutes": window_minutes, "summary": {"total_try_ons": self.loads}}


def test_realtime_snapshot_is_kept_in_memory_for_short_polling_interval() -> None:
    realtime = RealtimeForTest()

    first = realtime.snapshot(window_minutes=60)
    second = realtime.snapshot(window_minutes=60)

    assert first["cache"] == "MISS"
    assert second["cache"] == "HIT"
    assert realtime.loads == 1


def test_realtime_snapshot_refreshes_and_rejects_unbounded_windows() -> None:
    realtime = RealtimeForTest()
    realtime.snapshot(window_minutes=60)
    realtime.now += 3

    assert realtime.snapshot(window_minutes=60)["cache"] == "MISS"
    assert realtime.loads == 2
    with pytest.raises(AdminRealtimeError):
        realtime.snapshot(window_minutes=10_081)
