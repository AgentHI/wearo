from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.private_storage import (
    PrivateObject,
    PrivateObjectError,
    PrivateObjectService,
)

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class MemoryBackend:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.items[key] = content

    def get(self, key: str) -> bytes | None:
        return self.items.get(key)

    def delete(self, key: str) -> None:
        self.items.pop(key, None)


class MemoryMetadata:
    def __init__(self) -> None:
        self.items: dict[UUID, PrivateObject] = {}

    def create(self, item: PrivateObject) -> None:
        self.items[item.asset_id] = item

    def get(self, asset_id: UUID) -> PrivateObject | None:
        return self.items.get(asset_id)

    def revoke(self, asset_id: UUID, deleted_at: datetime) -> bool:
        item = self.items.get(asset_id)
        if item is None or item.deleted_at is not None:
            return False
        self.items[asset_id] = replace(item, deleted_at=deleted_at, generation=item.generation + 1)
        return True


def make_service() -> tuple[PrivateObjectService, MemoryBackend, MemoryMetadata]:
    backend, metadata = MemoryBackend(), MemoryMetadata()
    return (
        PrivateObjectService(backend, metadata, signing_key=b"wearo-private-signing-key-32bytes!"),
        backend,
        metadata,
    )


def test_private_object_requires_owner_and_short_lived_token() -> None:
    service, _, _ = make_service()
    owner = uuid4()
    item = service.store(owner, b"image-bytes", "image/jpeg")
    token = service.issue_read_token(item.asset_id, owner, now=NOW)
    assert service.read(token, now=NOW) == b"image-bytes"
    with pytest.raises(PrivateObjectError):
        service.issue_read_token(item.asset_id, uuid4(), now=NOW)
    with pytest.raises(PrivateObjectError):
        service.read(token, now=NOW + timedelta(minutes=6))


def test_tamper_and_delete_revoke_access_without_existence_leak() -> None:
    service, backend, _ = make_service()
    owner = uuid4()
    item = service.store(owner, b"image-bytes", "image/png")
    token = service.issue_read_token(item.asset_id, owner, now=NOW)
    with pytest.raises(PrivateObjectError, match="unavailable"):
        service.read(token + "x", now=NOW)
    service.delete(item.asset_id, owner, now=NOW)
    assert item.object_key not in backend.items
    with pytest.raises(PrivateObjectError, match="unavailable"):
        service.read(token, now=NOW)


def test_content_type_empty_content_and_long_ttl_fail_closed() -> None:
    service, _, _ = make_service()
    owner = uuid4()
    with pytest.raises(PrivateObjectError):
        service.store(owner, b"", "image/jpeg")
    with pytest.raises(PrivateObjectError):
        service.store(owner, b"x", "text/html")
    item = service.store(owner, b"x", "image/webp")
    with pytest.raises(ValueError):
        service.issue_read_token(item.asset_id, owner, now=NOW, ttl=timedelta(hours=1))
