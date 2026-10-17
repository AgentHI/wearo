from __future__ import annotations

import io
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

InputRole = Literal["PERSON", "GARMENT"]


class ImageInputError(ValueError):
    """Raised when an uploaded image cannot be prepared safely."""


@dataclass(frozen=True)
class PreparedImage:
    content: bytes
    mime_type: str
    width: int
    height: int
    original_bytes: int
    processing_ms: float
    transformed: bool


class ImageInputPreprocessor:
    """Create high-detail provider inputs without changing stored originals."""

    version = "v1"
    supported_formats = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    maximum_pixels = 40_000_000
    maximum_edge = 2_048
    passthrough_bytes = 3 * 1024 * 1024

    def prepare(self, content: bytes, mime_type: str, role: InputRole) -> PreparedImage:
        started = perf_counter()
        normalized_type = mime_type.split(";", maxsplit=1)[0].strip().lower()
        if normalized_type not in self.supported_formats.values() or not content:
            raise ImageInputError("unsupported image input")
        try:
            with Image.open(io.BytesIO(content)) as source:
                source_format = source.format
                if source_format not in self.supported_formats:
                    raise ImageInputError("unsupported image input")
                if self.supported_formats[source_format] != normalized_type:
                    raise ImageInputError("image content type does not match its data")
                width, height = source.size
                if width < 64 or height < 64 or width * height > self.maximum_pixels:
                    raise ImageInputError("invalid image dimensions")
                orientation = source.getexif().get(274, 1)
                source.load()
                needs_resize = max(width, height) > self.maximum_edge
                needs_encoding = (
                    orientation != 1 or needs_resize or len(content) > self.passthrough_bytes
                )
                if not needs_encoding:
                    return PreparedImage(
                        content,
                        normalized_type,
                        width,
                        height,
                        len(content),
                        (perf_counter() - started) * 1_000,
                        False,
                    )

                prepared = ImageOps.exif_transpose(source)
                if max(prepared.size) > self.maximum_edge:
                    prepared.thumbnail(
                        (self.maximum_edge, self.maximum_edge), Image.Resampling.LANCZOS
                    )
                output = io.BytesIO()
                has_alpha = "A" in prepared.getbands()
                if role == "GARMENT" and (has_alpha or source_format == "PNG"):
                    prepared.save(output, format="WEBP", lossless=True, method=4)
                    output_type = "image/webp"
                else:
                    if has_alpha:
                        background = Image.new("RGB", prepared.size, "white")
                        background.paste(prepared, mask=prepared.getchannel("A"))
                        prepared = background
                    elif prepared.mode != "RGB":
                        prepared = prepared.convert("RGB")
                    prepared.save(
                        output,
                        format="JPEG",
                        quality=95 if role == "GARMENT" else 92,
                        subsampling=0,
                        optimize=True,
                    )
                    output_type = "image/jpeg"
                encoded = output.getvalue()
                if role == "GARMENT" and len(encoded) > 7 * 1024 * 1024:
                    output = io.BytesIO()
                    prepared.save(
                        output,
                        format="WEBP",
                        quality=95,
                        alpha_quality=100,
                        method=4,
                    )
                    encoded = output.getvalue()
                    output_type = "image/webp"
                if not encoded:
                    raise ImageInputError("image optimization failed")
                return PreparedImage(
                    encoded,
                    output_type,
                    prepared.width,
                    prepared.height,
                    len(content),
                    (perf_counter() - started) * 1_000,
                    True,
                )
        except (ImageInputError, UnidentifiedImageError, OSError, ValueError):
            raise ImageInputError("invalid image input") from None


def detect_image_mime(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None
