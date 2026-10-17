from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID


class LifecycleError(ValueError):
    pass


@dataclass(frozen=True)
class RetentionPolicy:
    result_ttl: timedelta = timedelta(days=30)
    item_ttl: timedelta = timedelta(days=30)
    rejected_ttl: timedelta = timedelta(hours=24)
    deletion_sla: timedelta = timedelta(hours=24)
    profile_inactivity_ttl: timedelta = timedelta(days=365)


@dataclass(frozen=True)
class PurgeCandidate:
    asset_id: UUID
    account_id: UUID
    object_key: str


class LifecycleStore(Protocol):
    def request_owner_deletion(
        self, asset_id: UUID, account_id: UUID, delete_after: datetime
    ) -> bool: ...
    def revoke_access(self, asset_id: UUID, revoked_at: datetime) -> None: ...
    def due_for_purge(self, at: datetime, limit: int) -> tuple[PurgeCandidate, ...]: ...
    def mark_deleted(self, asset_id: UUID, deleted_at: datetime) -> None: ...
    def mark_purge_failed(self, asset_id: UUID, failed_at: datetime) -> None: ...


class BlobDeleter(Protocol):
    def delete(self, object_key: str) -> None: ...


class RetentionService:
    def __init__(
        self, store: LifecycleStore, blobs: BlobDeleter, policy: RetentionPolicy | None = None
    ) -> None:
        self.store, self.blobs = store, blobs
        self.policy = policy or RetentionPolicy()

    def request_delete(
        self, asset_id: UUID, account_id: UUID, *, now: datetime | None = None
    ) -> datetime:
        current = now or datetime.now(UTC)
        delete_after = current + self.policy.deletion_sla
        if not self.store.request_owner_deletion(asset_id, account_id, delete_after):
            raise LifecycleError("asset unavailable")
        self.store.revoke_access(asset_id, current)
        return delete_after

    def purge_due(self, *, now: datetime | None = None, limit: int = 100) -> tuple[UUID, ...]:
        current = now or datetime.now(UTC)
        deleted: list[UUID] = []
        for item in self.store.due_for_purge(current, limit):
            try:
                self.blobs.delete(item.object_key)
                self.store.mark_deleted(item.asset_id, current)
                deleted.append(item.asset_id)
            except OSError:
                self.store.mark_purge_failed(item.asset_id, current)
        return tuple(deleted)
