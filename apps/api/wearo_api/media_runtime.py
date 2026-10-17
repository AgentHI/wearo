from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import Engine, text

from .image_inputs import ImageInputError, ImageInputPreprocessor, InputRole, detect_image_mime


class MediaRuntimeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StoredMedia:
    asset_id: UUID
    account_id: UUID
    purpose: str
    mime_type: str
    size_bytes: int


class FilesystemPrivateBlobStore:
    """Non-public local blob backend for development and single-host beta deployments."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def put(self, key: str, content: bytes) -> None:
        target = self._path(key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        temporary.replace(target)

    def get(self, key: str) -> bytes | None:
        target = self._path(key)
        try:
            return target.read_bytes()
        except FileNotFoundError:
            return None

    def delete(self, key: str) -> None:
        for candidate in (
            key,
            f"{key}.prepared-{ImageInputPreprocessor.version}-person",
            f"{key}.prepared-{ImageInputPreprocessor.version}-garment",
        ):
            try:
                self._path(candidate).unlink()
            except FileNotFoundError:
                continue

    def _path(self, key: str) -> Path:
        if not key.startswith("private/"):
            raise MediaRuntimeError("ASSET_UNAVAILABLE", "Private asset is unavailable.")
        target = (self.root / key).resolve()
        if self.root not in target.parents:
            raise MediaRuntimeError("ASSET_UNAVAILABLE", "Private asset is unavailable.")
        return target


class PostgresMediaRuntime:
    maximum_bytes = 15 * 1024 * 1024
    mime_formats = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/webp": "WEBP",
    }
    purposes = {"PERSON": "PERSON_SOURCE", "PRODUCT": "PRODUCT_SOURCE"}

    def __init__(
        self,
        engine: Engine,
        blobs: FilesystemPrivateBlobStore,
        preprocessor: ImageInputPreprocessor | None = None,
    ) -> None:
        self.engine = engine
        self.blobs = blobs
        self.preprocessor = preprocessor or ImageInputPreprocessor()

    def store(
        self, account_id: UUID, *, kind: str, content: bytes, content_type: str
    ) -> StoredMedia:
        if kind not in self.purposes:
            raise MediaRuntimeError("UNSUPPORTED_IMAGE", "Upload a JPEG, PNG, or WebP image.")
        return self._store(account_id, self.purposes[kind], content, content_type)

    def store_result(self, account_id: UUID, content: bytes, content_type: str) -> UUID:
        return self._store(account_id, "RENDER_RESULT", content, content_type).asset_id

    def _store(
        self, account_id: UUID, purpose: str, content: bytes, content_type: str
    ) -> StoredMedia:
        normalized_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        if normalized_type not in self.mime_formats:
            raise MediaRuntimeError("UNSUPPORTED_IMAGE", "Upload a JPEG, PNG, or WebP image.")
        if not content or len(content) > self.maximum_bytes:
            raise MediaRuntimeError("INVALID_IMAGE_SIZE", "Upload an image under 15 MB.")
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format != self.mime_formats[normalized_type]:
                    raise UnidentifiedImageError
                width, height = image.size
                if width < 64 or height < 64 or width * height > 40_000_000:
                    raise UnidentifiedImageError
                image.load()
        except (UnidentifiedImageError, OSError, ValueError):
            raise MediaRuntimeError(
                "INVALID_IMAGE_CONTENT", "The uploaded file is not a safe supported image."
            ) from None

        digest = hashlib.sha256(content).hexdigest()
        if purpose in self.purposes.values():
            with self.engine.connect() as connection:
                existing = connection.execute(
                    text(
                        """
                        SELECT asset_id, object_key, mime_type
                        FROM media_assets
                        WHERE account_id = :account
                          AND purpose = :purpose
                          AND content_hash = :hash
                          AND deletion_state = 'RETAINED'
                          AND (delete_after IS NULL OR delete_after > now())
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"account": account_id, "purpose": purpose, "hash": digest},
                ).one_or_none()
            if existing is not None and self.blobs.get(existing.object_key) == content:
                return StoredMedia(
                    asset_id=existing.asset_id,
                    account_id=account_id,
                    purpose=purpose,
                    mime_type=existing.mime_type,
                    size_bytes=len(content),
                )

        asset_id = uuid4()
        object_key = f"private/{account_id.hex}/{asset_id.hex}"
        self.blobs.put(object_key, content)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO media_assets
                            (
                                asset_id,
                                account_id,
                                object_key,
                                content_hash,
                                mime_type,
                                purpose,
                                retention_state,
                                delete_after
                            )
                        VALUES
                            (
                                :asset,
                                :account,
                                :key,
                                :hash,
                                :mime,
                                :purpose,
                                :retention_state,
                                :delete_after
                            )
                        """
                    ),
                    {
                        "asset": asset_id,
                        "account": account_id,
                        "key": object_key,
                        "hash": digest,
                        "mime": normalized_type,
                        "purpose": purpose,
                        "retention_state": ("ACTIVE" if purpose == "PERSON_SOURCE" else "EXPIRING"),
                        "delete_after": (
                            None
                            if purpose == "PERSON_SOURCE"
                            else datetime.now(UTC) + timedelta(days=30)
                        ),
                    },
                )
        except Exception:
            self.blobs.delete(object_key)
            raise
        return StoredMedia(
            asset_id=asset_id,
            account_id=account_id,
            purpose=purpose,
            mime_type=normalized_type,
            size_bytes=len(content),
        )

    def read_owned(self, asset_id: UUID, account_id: UUID) -> tuple[bytes, str]:
        object_key, content_hash, mime_type = self._owned_metadata(asset_id, account_id)
        return self._verified_blob(object_key, content_hash), mime_type

    def read_prepared(self, asset_id: UUID, account_id: UUID, role: InputRole) -> tuple[bytes, str]:
        object_key, content_hash, mime_type = self._owned_metadata(asset_id, account_id)
        cache_key = f"{object_key}.prepared-{self.preprocessor.version}-{role.lower()}"
        cached = self.blobs.get(cache_key)
        if cached is not None:
            cached_type = detect_image_mime(cached)
            if cached_type is not None:
                return cached, cached_type
        content = self._verified_blob(object_key, content_hash)
        try:
            prepared = self.preprocessor.prepare(content, mime_type, role)
        except ImageInputError:
            raise MediaRuntimeError(
                "INVALID_IMAGE_CONTENT", "The uploaded file is not a safe supported image."
            ) from None
        self.blobs.put(cache_key, prepared.content)
        return prepared.content, prepared.mime_type

    def store_progressive_preview(self, job_id: UUID, content: bytes) -> None:
        if detect_image_mime(content) is None:
            raise MediaRuntimeError("INVALID_IMAGE_CONTENT", "Invalid progressive preview.")
        self.blobs.put(f"private/previews/{job_id.hex}", content)

    def read_progressive_preview(self, job_id: UUID) -> tuple[bytes, str] | None:
        content = self.blobs.get(f"private/previews/{job_id.hex}")
        if content is None:
            return None
        mime_type = detect_image_mime(content)
        return (content, mime_type) if mime_type is not None else None

    def clear_progressive_preview(self, job_id: UUID) -> None:
        self.blobs.delete(f"private/previews/{job_id.hex}")

    def _owned_metadata(self, asset_id: UUID, account_id: UUID) -> tuple[str, str, str]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT object_key, content_hash, mime_type
                    FROM media_assets
                    WHERE asset_id = :asset
                      AND account_id = :account
                      AND deletion_state = 'RETAINED'
                    """
                ),
                {"asset": asset_id, "account": account_id},
            ).one_or_none()
        if row is None:
            raise MediaRuntimeError("ASSET_UNAVAILABLE", "Private asset is unavailable.")
        return row.object_key, row.content_hash, row.mime_type

    def _verified_blob(self, object_key: str, content_hash: str) -> bytes:
        content = self.blobs.get(object_key)
        if content is None or not hashlib.sha256(content).hexdigest() == content_hash:
            raise MediaRuntimeError("ASSET_UNAVAILABLE", "Private asset is unavailable.")
        return content
