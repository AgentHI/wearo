from __future__ import annotations

import io

from PIL import Image, ImageChops

from apps.api.wearo_api.image_watermark import apply_generated_image_watermark


def source_image(mime_type: str = "image/png") -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", (1000, 1200), "#c6a7cf")
    image.save(output, "JPEG" if mime_type == "image/jpeg" else "PNG")
    return output.getvalue()


def test_wearo_brand_is_added_only_to_bottom_right_corner() -> None:
    source = source_image()
    result, mime_type = apply_generated_image_watermark(source, "image/png")
    with Image.open(io.BytesIO(source)) as before, Image.open(io.BytesIO(result)) as after:
        assert mime_type == "image/png" and after.size == before.size
        assert after.convert("RGB").getpixel((500, 500)) == before.getpixel((500, 500))
        changed = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
        assert changed.getbbox() is not None
        left, top, right, bottom = changed.getbbox()
        assert left > 850 and top > 1080 and right <= 1000 and bottom <= 1200
        changed_pixels = sum(changed.convert("L").histogram()[1:])
        assert changed_pixels / (before.width * before.height) < 0.01


def test_b2b2c_company_name_is_added_to_top_left_and_jpeg_is_preserved() -> None:
    source = source_image("image/jpeg")
    result, mime_type = apply_generated_image_watermark(
        source, "image/jpeg", company_name="Acme Fashions"
    )
    with Image.open(io.BytesIO(result)) as image:
        assert mime_type == "image/jpeg" and image.format == "JPEG"
        assert image.getpixel((35, 35)) != (198, 167, 207)
