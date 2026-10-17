from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4


class PrivateObjectError(ValueError):
    """Generic private-object denial."""


@dataclass(frozen=True)
class PrivateObject:
    asset_id: UUID
    owner_account_id: UUID
    object_key: str
    content_type: str
    content_hash: str
    generation: int
    deleted_at: datetime | None = None


class ObjectBackend(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...


class ObjectMetadataStore(Protocol):
    def create(self, item: PrivateObject) -> None: ...
    def get(self, asset_id: UUID) -> PrivateObject | None: ...
    def revoke(self, asset_id: UUID, deleted_at: datetime) -> bool: ...


class PrivateObjectService:
    def __init__(
        self, backend: ObjectBackend, metadata: ObjectMetadataStore, *, signing_key: bytes
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError("signing key must contain at least 32 bytes")
        self.backend = backend
        self.metadata = metadata
        self.signing_key = signing_key

    def store(self, owner_account_id: UUID, content: bytes, content_type: str) -> PrivateObject:
        if content_type not in {"image/jpeg", "image/png", "image/webp"} or not content:
            raise PrivateObjectError("unsupported private object")
        item = PrivateObject(
            asset_id=uuid4(),
            owner_account_id=owner_account_id,
            object_key=f"private/{uuid4().hex}",
            content_type=content_type,
            content_hash=hashlib.sha256(content).hexdigest(),
            generation=1,
        )
        self.backend.put(item.object_key, content, content_type)
        self.metadata.create(item)
        return item

    def issue_read_token(
        self,
        asset_id: UUID,
        owner_account_id: UUID,
        *,
        now: datetime | None = None,
        ttl: timedelta = timedelta(minutes=5),
    ) -> str:
        current = now or datetime.now(UTC)
        if ttl <= timedelta(0) or ttl > timedelta(minutes=15):
            raise ValueError("signed access TTL must be between zero and 15 minutes")
        item = self._owned(asset_id, owner_account_id)
        payload = {
            "a": str(item.asset_id),
            "e": int((current + ttl).timestamp()),
            "g": item.generation,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=")
        signature = hmac.new(self.signing_key, encoded, hashlib.sha256).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def read(self, token: str, *, now: datetime | None = None) -> bytes:
        current = now or datetime.now(UTC)
        try:
            raw_payload, raw_signature = token.split(".", 1)
            encoded = raw_payload.encode()
            expected = hmac.new(self.signing_key, encoded, hashlib.sha256).digest()
            signature = base64.urlsafe_b64decode(raw_signature + "=" * (-len(raw_signature) % 4))
            if not hmac.compare_digest(expected, signature):
                raise ValueError
            payload = json.loads(
                base64.urlsafe_b64decode(raw_payload + "=" * (-len(raw_payload) % 4))
            )
            asset_id = UUID(payload["a"])
            expires_at = datetime.fromtimestamp(payload["e"], UTC)
            generation = int(payload["g"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise PrivateObjectError("private object unavailable") from None
        item = self.metadata.get(asset_id)
        if (
            item is None
            or item.deleted_at is not None
            or item.generation != generation
            or expires_at <= current
        ):
            raise PrivateObjectError("private object unavailable")
        content = self.backend.get(item.object_key)
        if content is None or hashlib.sha256(content).hexdigest() != item.content_hash:
            raise PrivateObjectError("private object unavailable")
        return content

    def delete(
        self, asset_id: UUID, owner_account_id: UUID, *, now: datetime | None = None
    ) -> None:
        item = self._owned(asset_id, owner_account_id)
        current = now or datetime.now(UTC)
        if not self.metadata.revoke(asset_id, current):
            raise PrivateObjectError("private object unavailable")
        self.backend.delete(item.object_key)

    def _owned(self, asset_id: UUID, owner_account_id: UUID) -> PrivateObject:
        item = self.metadata.get(asset_id)
        if item is None or item.owner_account_id != owner_account_id or item.deleted_at is not None:
            raise PrivateObjectError("private object unavailable")
        return item
