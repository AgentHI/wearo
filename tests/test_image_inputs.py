from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from PIL import Image
from sqlalchemy import Engine

from apps.api.wearo_api.image_inputs import ImageInputPreprocessor
from apps.api.wearo_api.media_runtime import FilesystemPrivateBlobStore, PostgresMediaRuntime


def encoded_image(
    size: tuple[int, int],
    *,
    image_format: str = "PNG",
    mode: str = "RGB",
    exif_orientation: int | None = None,
) -> bytes:
    output = io.BytesIO()
    image = Image.new(mode, size, (80, 120, 180, 180) if mode == "RGBA" else (80, 120, 180))
    exif = Image.Exif()
    if exif_orientation is not None:
        exif[274] = exif_orientation
    image.save(output, format=image_format, exif=exif)
    return output.getvalue()


def test_small_valid_input_is_not_reencoded() -> None:
    original = encoded_image((800, 1_000))
    prepared = ImageInputPreprocessor().prepare(original, "image/png", "PERSON")
    assert prepared.content == original
    assert prepared.mime_type == "image/png"
    assert prepared.transformed is False
    assert (prepared.width, prepared.height) == (800, 1_000)


def test_large_person_is_exif_rotated_resized_without_aspect_distortion() -> None:
    original = encoded_image((1_200, 3_000), image_format="JPEG", exif_orientation=6)
    prepared = ImageInputPreprocessor().prepare(original, "image/jpeg", "PERSON")
    with Image.open(io.BytesIO(prepared.content)) as result:
        assert result.size == (2_048, 819)
        assert result.getexif().get(274, 1) == 1
    assert prepared.transformed is True
    assert prepared.mime_type == "image/jpeg"
    assert original.startswith(b"\xff\xd8\xff")


def test_large_garment_uses_high_detail_alpha_preserving_output() -> None:
    original = encoded_image((2_500, 1_000), mode="RGBA")
    prepared = ImageInputPreprocessor().prepare(original, "image/png", "GARMENT")
    with Image.open(io.BytesIO(prepared.content)) as result:
        assert result.size == (2_048, 819)
        assert "A" in result.getbands()
    assert prepared.mime_type == "image/webp"
    assert prepared.transformed is True


def test_processed_input_is_cached_by_unchanged_content(tmp_path: Path) -> None:
    original = encoded_image((2_500, 1_000), image_format="JPEG")

    class CountingPreprocessor(ImageInputPreprocessor):
        calls = 0

        def prepare(self, content: bytes, mime_type: str, role: Any) -> Any:
            self.calls += 1
            return super().prepare(content, mime_type, role)

    class Media(PostgresMediaRuntime):
        original_reads = 0

        def _owned_metadata(self, asset_id: UUID, account_id: UUID) -> tuple[str, str, str]:
            return (
                f"private/{account_id.hex}/{asset_id.hex}",
                "unchanged-content-hash",
                "image/jpeg",
            )

        def _verified_blob(self, object_key: str, content_hash: str) -> bytes:
            self.original_reads += 1
            return original

    preprocessor = CountingPreprocessor()
    media = Media(
        cast(Engine, object()), FilesystemPrivateBlobStore(tmp_path), preprocessor=preprocessor
    )
    asset_id, account_id = uuid4(), uuid4()
    first = media.read_prepared(asset_id, account_id, "GARMENT")
    second = media.read_prepared(asset_id, account_id, "GARMENT")
    assert first == second
    assert preprocessor.calls == 1
    assert media.original_reads == 1


def test_progressive_preview_is_private_ephemeral_blob(tmp_path: Path) -> None:
    media = PostgresMediaRuntime(cast(Engine, object()), FilesystemPrivateBlobStore(tmp_path))
    job_id = uuid4()
    partial = encoded_image((320, 480))
    media.store_progressive_preview(job_id, partial)
    assert media.read_progressive_preview(job_id) == (partial, "image/png")
    media.clear_progressive_preview(job_id)
    assert media.read_progressive_preview(job_id) is None


def test_deleting_asset_family_removes_original_thumbnail_and_generated_copies(
    tmp_path: Path,
) -> None:
    blobs = FilesystemPrivateBlobStore(tmp_path)
    key = "private/account/asset"
    person_key = f"{key}.prepared-{ImageInputPreprocessor.version}-person"
    garment_key = f"{key}.prepared-{ImageInputPreprocessor.version}-garment"
    thumbnail_key = f"{key}.thumbnail.webp"
    optimized_key = f"{key}.optimized.webp"
    generated_key = f"{key}.generated-background-removed.png"
    candidates = (
        key,
        person_key,
        garment_key,
        thumbnail_key,
        optimized_key,
        generated_key,
    )
    for candidate in candidates:
        blobs.put(candidate, b"image")
    blobs.delete_asset_family(key)
    assert all(blobs.get(candidate) is None for candidate in candidates)

    blobs.delete_asset_family(key)
    assert all(blobs.get(candidate) is None for candidate in candidates)
