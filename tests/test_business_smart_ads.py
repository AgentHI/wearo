import io
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from PIL import Image
from pydantic import ValidationError

from apps.api.wearo_api.business_smart_ads import (
    MAX_DAILY_GENERATIONS,
    OpenAISmartAdGenerator,
    PromotedSmartAdGenerator,
    SmartAdError,
    normalize_creative,
    smart_ad_try_on_url,
)
from apps.cost_lab_api.adapters import GenerationResult, OpenAICompatibleAdapter
from apps.cost_lab_api.app import AdvertisementProductionModelBody
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


def test_smart_ad_generator_uses_the_selected_promoted_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    generator = PromotedSmartAdGenerator(cast(Any, object()), "")
    monkeypatch.setenv("WEARO_SELECTED_AD_TEST_KEY", "secret")
    monkeypatch.setattr(
        generator,
        "_selected_route",
        lambda: {
            "release_id": UUID("49bf272c-cac8-4452-8aef-b430c4326f80"),
            "approved_quality_levels": ["HIGH"],
            "api_identifier": "promoted-image-model",
            "provider_type": "OPENAI_COMPATIBLE",
            "api_base_url": "https://images.example/v1",
            "secret_ciphertext": None,
            "secret_reference": "env:WEARO_SELECTED_AD_TEST_KEY",
            "quality": "HIGH",
            "quality_settings": {},
            "provider_quality": None,
            "request_parameters": {},
        },
    )

    def generate(self: OpenAICompatibleAdapter, **request: object) -> GenerationResult:
        captured.update({"base_url": self.base_url, **request})
        return GenerationResult(image_bytes(), "request-1", {}, {}, 10)

    monkeypatch.setattr(OpenAICompatibleAdapter, "generate", generate)

    result = generator.generate(
        "A premium launch",
        (image_bytes(), "image/png"),
        (image_bytes((800, 1200)), "image/png"),
        safety_identifier="stable-business",
    )

    assert result
    assert captured["base_url"] == "https://images.example/v1"
    assert captured["model"] == "promoted-image-model"
    assert len(cast(list[bytes], captured["images"])) == 2
    parameters = cast(dict[str, object], captured["parameters"])
    assert parameters["quality"] == "high"
    assert parameters["size"] == "1664x2496"
    assert parameters["safety_identifier"] == "stable-business"


def test_advertisement_model_selection_accepts_promoted_or_manual_models() -> None:
    promoted_migration = Path(
        "apps/api/migrations/versions/20261128_0105_advertisement_production_model.py"
    )
    manual_migration = Path(
        "apps/api/migrations/versions/20261128_0106_manual_advertisement_model.py"
    )
    promoted_migration_source = promoted_migration.read_text()
    manual_migration_source = manual_migration.read_text()
    cost_lab_api = Path("apps/cost_lab_api/app.py").read_text()
    smart_ads = Path("apps/api/wearo_api/business_smart_ads.py").read_text()
    cost_lab_ui = Path("packages/cost-lab-ui/src/index.js").read_text()

    assert validate_revision(promoted_migration) == "20261128_0105"
    assert validate_revision(manual_migration) == "20261128_0106"
    assert "ADD COLUMN advertisement_model" in promoted_migration_source
    assert "uq_active_advertisement_production_model" in promoted_migration_source
    assert "ALTER TABLE cost_lab.ai_models" in manual_migration_source
    assert "uq_cost_lab_advertisement_model" in manual_migration_source
    assert '"/api/cost-lab/production-models/advertisement-model"' in cost_lab_api
    assert "r.release_id=:release AND r.retired_at IS NULL" in cost_lab_api
    assert "provider_id and api_identifier are required" in cost_lab_api
    assert "INSERT INTO cost_lab.ai_models" in cost_lab_api
    assert "information_schema.columns" in cost_lab_api
    assert "WHERE m.advertisement_model AND m.enabled AND p.enabled" in smart_ads
    promoted_view = cost_lab_ui.split("function promotedModelsView()", 1)[1].split(
        "async function attachFinalChecks", 1
    )[0]
    assert promoted_view.index('id="production-model-list"') < promoted_view.index(
        'id="advertisement-model-picker"'
    )
    assert 'aria-label="Save priorities"' in cost_lab_ui
    assert 'aria-label="Save advertisement model"' in cost_lab_ui
    assert "cost-advertisement-model__current" in cost_lab_ui
    assert "Current active model" in cost_lab_ui
    assert 'name="provider_id"' in cost_lab_ui
    assert 'name="api_identifier"' in cost_lab_ui
    assert 'placeholder="gpt-image-2"' in cost_lab_ui


def test_advertisement_model_request_requires_one_complete_selection() -> None:
    release_id = UUID("49bf272c-cac8-4452-8aef-b430c4326f80")
    provider_id = UUID("03730145-20e9-4d49-877c-6216008f703f")

    promoted = AdvertisementProductionModelBody(release_id=release_id)
    manual = AdvertisementProductionModelBody(
        provider_id=provider_id, api_identifier="  gpt-image-2  "
    )

    assert promoted.release_id == release_id
    assert manual.api_identifier == "gpt-image-2"
    with pytest.raises(ValidationError):
        AdvertisementProductionModelBody()
    with pytest.raises(ValidationError):
        AdvertisementProductionModelBody(provider_id=provider_id)
    with pytest.raises(ValidationError):
        AdvertisementProductionModelBody(
            release_id=release_id,
            provider_id=provider_id,
            api_identifier="gpt-image-2",
        )


def test_smart_ads_schema_and_service_keep_the_feature_separate() -> None:
    migration = Path("apps/api/migrations/versions/20261122_0095_business_smart_ads.py")
    email_migration = Path("apps/api/migrations/versions/20261122_0096_smart_ad_email_subject.py")
    source = migration.read_text()
    email_source = email_migration.read_text()
    service = Path("apps/api/wearo_api/business_smart_ads.py").read_text()

    assert validate_revision(migration) == "20261122_0095"
    assert validate_revision(email_migration) == "20261122_0096"
    assert "business_smart_ads" in source
    assert "store_advertisements" not in source
    assert "'{{advertisement_title}}'" in source
    assert "SET subject = '{{advertisement_title}}'" in email_source
    assert "count(DISTINCT person.person_id)" in service
    assert "person.gender='female'" in service
    assert "observation.marketing_eligible=true" in service
    assert "SMART_AD_BUSINESS_LOGO_REQUIRED" in service
    assert "company_logo=business_logo" in service
    assert "SMART_AD_GENERATION_IN_PROGRESS" in service
    assert "generation_in_progress" in service
    assert "SELECT operating_profile" in service
    assert '"operating_profile": operating_profile' in service
    assert "GENERATION_TIMEOUT" in service
    assert "communication_jobs" in service
    assert "template_key,recipient" in service
    assert MAX_DAILY_GENERATIONS == 2


def test_smart_ad_retention_requires_the_admin_managed_record_to_be_deleted() -> None:
    retention = Path("apps/api/wearo_api/postgres_retention.py").read_text()
    migration = Path("apps/api/migrations/versions/20261128_0104_protect_smart_ad_assets.py")
    migration_source = migration.read_text()

    assert validate_revision(migration) == "20261128_0104"
    assert "candidate.purpose = 'SMART_AD'" in retention
    assert "FROM business_smart_ads AS ad" in retention
    assert "FROM business_smart_ad_generations AS generation" in retention
    assert "SET deletion_state = 'RETAINED'" in migration_source
    assert "asset.deletion_state <> 'DELETED'" in migration_source


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
    assert '"/api/v1/business/tenants/{tenant_id}/smart-ad-schedules/{schedule_id}"' in source


def test_smart_ad_schedules_can_be_updated_and_deleted_before_delivery() -> None:
    service = Path("apps/api/wearo_api/business_smart_ads.py").read_text()
    api = Path("apps/api/wearo_api/http_api.py").read_text()

    assert "def update_schedule(" in service
    assert "def delete_schedule(" in service
    assert "SMART_AD_SCHEDULE_UPDATED" in service
    assert "SMART_AD_SCHEDULE_DELETED" in service
    assert "status IN ('PROCESSING','DELIVERED')" in service
    assert "def update_business_smart_ad_schedule(" in api
    assert "def delete_business_smart_ad_schedule(" in api
    assert "SMART_AD_SCHEDULE_LOCKED" in api
