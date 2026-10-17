from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.retention import LifecycleError, PurgeCandidate, RetentionService

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class Store:
    def __init__(self, item: PurgeCandidate) -> None:
        self.item = item
        self.revoked: list[UUID] = []
        self.deleted: list[UUID] = []
        self.failed: list[UUID] = []

    def request_owner_deletion(
        self, asset_id: UUID, account_id: UUID, delete_after: datetime
    ) -> bool:
        return asset_id == self.item.asset_id and account_id == self.item.account_id

    def revoke_access(self, asset_id: UUID, revoked_at: datetime) -> None:
        self.revoked.append(asset_id)

    def due_for_purge(self, at: datetime, limit: int) -> tuple[PurgeCandidate, ...]:
        return (self.item,)

    def mark_deleted(self, asset_id: UUID, deleted_at: datetime) -> None:
        self.deleted.append(asset_id)

    def mark_purge_failed(self, asset_id: UUID, failed_at: datetime) -> None:
        self.failed.append(asset_id)


class Blobs:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.keys: list[str] = []

    def delete(self, object_key: str) -> None:
        if self.fail:
            raise OSError("temporary")
        self.keys.append(object_key)


def test_owner_deletion_revokes_now_and_schedules_24_hour_purge() -> None:
    item = PurgeCandidate(uuid4(), uuid4(), "private/key")
    store = Store(item)
    delete_after = RetentionService(store, Blobs()).request_delete(
        item.asset_id, item.account_id, now=NOW
    )
    assert store.revoked == [item.asset_id] and delete_after == NOW + timedelta(hours=24)
    with pytest.raises(LifecycleError):
        RetentionService(store, Blobs()).request_delete(item.asset_id, uuid4(), now=NOW)


def test_scheduler_deletes_blob_then_marks_tombstone() -> None:
    item = PurgeCandidate(uuid4(), uuid4(), "private/key")
    store, blobs = Store(item), Blobs()
    assert RetentionService(store, blobs).purge_due(now=NOW) == (item.asset_id,)
    assert blobs.keys == [item.object_key] and store.deleted == [item.asset_id]


def test_failed_blob_delete_is_retryable_and_not_marked_deleted() -> None:
    item = PurgeCandidate(uuid4(), uuid4(), "private/key")
    store = Store(item)
    assert RetentionService(store, Blobs(True)).purge_due(now=NOW) == ()
    assert store.failed == [item.asset_id] and not store.deleted
