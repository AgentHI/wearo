from io import BytesIO

from PIL import Image

from apps.api.wearo_api.business_shop import qr_poster


def test_qr_poster_is_a_downloadable_png_with_poster_dimensions() -> None:
    content = qr_poster("https://wearo.example/shop/tenant-id?key=public-token", "Wearo Atelier")
    image = Image.open(BytesIO(content))
    assert image.format == "PNG"
    assert image.size == (1122, 1402)
