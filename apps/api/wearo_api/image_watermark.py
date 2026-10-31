from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

BRAND_ASSET = Path(__file__).with_name("assets") / "wearo-brand.png"


class ImageWatermarkError(ValueError):
    """Raised when a generated image cannot be safely watermarked."""


@lru_cache(maxsize=1)
def _brand_logo() -> Image.Image:
    with Image.open(BRAND_ASSET) as source:
        logo = source.convert("RGB")
    # Convert the existing white-background asset into a transparent overlay. The
    # soft ramp retains antialiased colored edges but drops white and near-white.
    alpha = ImageOps.invert(logo.convert("L")).point(
        lambda value: 0 if value < 8 else min(255, round((value - 8) * 2.5))
    )
    logo = logo.convert("RGBA")
    logo.putalpha(alpha)
    bounds = alpha.getbbox()
    return logo.crop(bounds) if bounds else logo


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def apply_generated_image_watermark(
    content: bytes,
    content_type: str,
    *,
    company_name: str | None = None,
) -> tuple[bytes, str]:
    """Add the Wearo brand and, for B2B2C renders, the sponsoring company name."""

    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = source.convert("RGBA")
    except (OSError, ValueError) as error:
        raise ImageWatermarkError("Generated image is not a supported raster image.") from error

    width, height = image.size
    shortest = min(width, height)
    margin = max(8, round(shortest * 0.015))

    logo = _brand_logo().copy()
    logo_width = max(52, round(width * 0.11))
    logo_width = min(logo_width, max(1, width - 2 * margin))
    logo_height = max(1, round(logo.height * logo_width / logo.width))
    max_logo_height = max(1, round(height * 0.075))
    if logo_height > max_logo_height:
        logo_height = max_logo_height
        logo_width = max(1, round(logo.width * logo_height / logo.height))
    logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
    logo.putalpha(logo.getchannel("A").point(lambda alpha: round(alpha * 0.58)))
    x = width - margin - logo.width
    y = height - margin - logo.height
    image.alpha_composite(logo, (x, y))

    label = (company_name or "").strip()
    if label:
        # Keep a long legal name compact and inside the corner treatment.
        label = label[:64]
        font_size = max(11, min(24, round(shortest * 0.022)))
        font = _font(font_size)
        max_text_width = max(1, round(width * 0.42))
        probe = ImageDraw.Draw(image)
        while font_size > 9 and probe.textbbox((0, 0), label, font=font)[2] > max_text_width:
            font_size -= 1
            font = _font(font_size)
        bounds = probe.textbbox((0, 0), label, font=font, stroke_width=1)
        text_width, text_height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        text_layer = Image.new("RGBA", (text_width + 4, text_height + 4), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_layer)
        text_draw.text(
            (2 - bounds[0], 2 - bounds[1]),
            label,
            font=font,
            fill=(65, 19, 70, 145),
            stroke_width=1,
            stroke_fill=(255, 255, 255, 120),
        )
        image.alpha_composite(text_layer, (margin, margin))

    normalized_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    output = io.BytesIO()
    if normalized_type == "image/jpeg":
        flattened = Image.new("RGB", image.size, "white")
        flattened.paste(image, mask=image.getchannel("A"))
        flattened.save(output, "JPEG", quality=92, optimize=True)
        return output.getvalue(), "image/jpeg"
    if normalized_type == "image/webp":
        image.save(output, "WEBP", quality=92, method=6)
        return output.getvalue(), "image/webp"
    image.save(output, "PNG", optimize=True)
    return output.getvalue(), "image/png"
