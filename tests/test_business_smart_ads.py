import io
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from PIL import Image

from apps.api.wearo_api.business_smart_ads import (
    MAX_DAILY_GENERATIONS,
    OpenAISmartAdGenerator,
    SmartAdError,
    normalize_creative,
    smart_ad_try_on_url,
)
from scripts.validate_migrations import validate_revision


def image_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "#c9a46b").save(output, "PNG")
    return output.getvalue()


def test_smart_ad_creative_is_normalized_for_portrait_campaigns() -> None:
    normalized = normalize_creative(image_bytes())

    with Image.open(io.BytesIO(normalized)) as result:
        assert result.size == (768, 1024)
        assert result.format == "JPEG"


def test_smart_ad_creative_rejects_non_images() -> None:
    with pytest.raises(SmartAdError, match="valid JPEG"):
        normalize_creative(b"not-an-image")


def test_smart_ad_try_on_url_opens_the_business_shop_with_campaign_context() -> None:
    token = UUID("8eb8f31b-13f4-4a14-9eef-b043902c18fd")

    result = smart_ad_try_on_url(
        "https://wearo.example/",
        "madhu-jewels",
        "public key",
        token,
    )

    assert result == (
        "https://wearo.example/shop/madhu-jewels?key=public+key"
        "&smart_ad=8eb8f31b-13f4-4a14-9eef-b043902c18fd"
    )


def test_smart_ad_generator_uses_jewellery_and_optional_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            import base64

            return {"data": [{"b64_json": base64.b64encode(image_bytes()).decode()}]}

    def post(url: str, **request: object) -> Response:
        captured.update({"url": url, **request})
        return Response()

    monkeypatch.setattr("apps.api.wearo_api.business_smart_ads.requests.post", post)
    generator = OpenAISmartAdGenerator("secret", "gpt-image-2")

    generated = generator.generate(
        "A festive concept",
        (image_bytes(), "image/png"),
        (image_bytes((800, 1200)), "image/png"),
        safety_identifier="stable-id",
    )

    assert generated
    assert captured["url"] == "https://api.openai.com/v1/images/edits"
    body = cast(dict[str, Any], captured["json"])
    assert len(body["images"]) == 2
    assert body["safety_identifier"] == "stable-id"
    assert body["size"] == "1024x1536"


def test_smart_ads_schema_and_service_keep_the_feature_separate() -> None:
    migration = Path("apps/api/migrations/versions/20261122_0095_business_smart_ads.py")
    source = migration.read_text()
    service = Path("apps/api/wearo_api/business_smart_ads.py").read_text()

    assert validate_revision(migration) == "20261122_0095"
    assert "business_smart_ads" in source
    assert "store_advertisements" not in source
    assert "count(DISTINCT person.person_id)" in service
    assert "person.gender='female'" in service
    assert "person.marketing_eligible=true" in service
    assert "communication_jobs" in service
    assert "template_key,recipient" in service
    assert MAX_DAILY_GENERATIONS == 2


def test_smart_ads_http_surface_covers_lifecycle_and_scheduling() -> None:
    source = Path("apps/api/wearo_api/http_api.py").read_text()

    for path in (
        '"/api/v1/business/tenants/{tenant_id}/smart-ads"',
        '"/api/v1/business/tenants/{tenant_id}/smart-ads/{smart_ad_id}/generate"',
        '"/api/v1/business/tenants/{tenant_id}/smart-ads/{smart_ad_id}/accept"',
        '"/api/v1/business/tenants/{tenant_id}/smart-ad-schedules"',
        '"/api/v1/public/smart-ads/{public_token}/image"',
        '"/api/v1/public/smart-ads/{public_token}/try-on-item"',
    ):
        assert path in source
