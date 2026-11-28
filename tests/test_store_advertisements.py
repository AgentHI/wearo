from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

from apps.api.wearo_api.store_advertisements import (
    CARD_HEIGHT,
    CARD_WIDTH,
    CostLabAdvertisementGenerator,
    StoreAdvertisementError,
    crop_card,
    validate_duration,
)
from apps.cost_lab_api.adapters import GenerationResult, OpenAICompatibleAdapter


def test_uploaded_advertisement_is_cropped_to_bounded_tryon_card() -> None:
    source = BytesIO()
    Image.new("RGB", (1600, 600), "purple").save(source, "PNG")

    result = crop_card(source.getvalue())

    with Image.open(BytesIO(result)) as card:
        assert card.size == (CARD_WIDTH, CARD_HEIGHT)
        assert card.format == "JPEG"


def test_store_advertisement_uses_the_dedicated_cost_lab_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    generator = CostLabAdvertisementGenerator(cast(Any, object()), "")
    monkeypatch.setenv("WEARO_SELECTED_STORE_AD_TEST_KEY", "secret")
    monkeypatch.setattr(
        generator,
        "_selected_route",
        lambda: {
            "release_id": None,
            "approved_quality_levels": None,
            "api_identifier": "gpt-image-2",
            "provider_type": "OPENAI_COMPATIBLE",
            "api_base_url": "https://images.example/v1",
            "secret_ciphertext": None,
            "secret_reference": "env:WEARO_SELECTED_STORE_AD_TEST_KEY",
            "quality": "HIGH",
            "quality_settings": {},
            "provider_quality": None,
            "request_parameters": {},
        },
    )

    def generate_from_prompt(
        self: OpenAICompatibleAdapter, **request: object
    ) -> GenerationResult:
        captured.update({"base_url": self.base_url, **request})
        source = BytesIO()
        Image.new("RGB", (768, 1024), "purple").save(source, "PNG")
        return GenerationResult(source.getvalue(), "request-1", {}, {}, 10)

    monkeypatch.setattr(OpenAICompatibleAdapter, "generate_from_prompt", generate_from_prompt)

    result = generator.generate("A festive collection")

    assert result
    assert captured["base_url"] == "https://images.example/v1"
    assert captured["model"] == "gpt-image-2"
    assert "A festive collection" in str(captured["prompt"])
    parameters = cast(dict[str, object], captured["parameters"])
    assert parameters["quality"] == "high"
    assert parameters["size"] == "1664x2496"
    assert parameters["output_format"] == "png"


def test_store_advertisement_runtime_no_longer_uses_an_env_model() -> None:
    source = Path("apps/api/wearo_api/http_api.py").read_text()
    wiring = source[source.index('"store_advertisements"') : source.index('"business_smart_ads"')]

    assert "CostLabAdvertisementGenerator" in wiring
    assert "WEARO_ADVERTISEMENT_AI_MODEL" not in wiring


def test_advertisement_schema_has_entitlement_attempt_cap_and_daily_activation() -> None:
    source = Path("apps/api/migrations/versions/20261031_0054_store_advertisements.py").read_text()
    assert '"advertisements_enabled"' in source
    assert "ai_attempts BETWEEN 0 AND 3" in source
    assert 'sa.PrimaryKeyConstraint("store_id", "active_date")' in source


def test_advertisement_list_query_uses_store_context_parameter_names() -> None:
    source = Path("apps/api/wearo_api/store_advertisements.py").read_text()
    assert "WHERE a.store_id=:store_id AND a.account_id=:account_id" in source
    assert "WHERE a.store_id=:store AND a.account_id=:account" not in source


def test_sponsored_advertisement_is_scoped_to_session_owner_and_ist_day() -> None:
    source = Path("apps/api/wearo_api/store_advertisements.py").read_text()
    assert "session.consumer_account_id=:consumer_account" in source
    assert "session.consumer_principal_id=:consumer_principal" in source
    assert "activation.active_date=(now() AT TIME ZONE 'Asia/Kolkata')::date" in source
    assert "session.store_id IS NULL AND selected_store.code='main'" in source


def test_store_can_remove_only_the_selected_day_activation() -> None:
    source = Path("apps/api/wearo_api/store_advertisements.py").read_text()
    assert "DELETE FROM store_advertisement_activations" in source
    assert "WHERE store_id=:store_id AND active_date=:active_date" in source


def test_advertisement_duration_requires_end_on_or_after_start() -> None:
    from datetime import date

    validate_duration(date(2026, 11, 1), date(2026, 11, 1))
    with pytest.raises(StoreAdvertisementError, match="end date"):
        validate_duration(date(2026, 11, 2), date(2026, 11, 1))


def test_duration_migration_backfills_existing_cards() -> None:
    source = Path(
        "apps/api/migrations/versions/20261031_0055_advertisement_duration.py"
    ).read_text()
    assert "ends_on >= starts_on" in source
    assert "UPDATE store_advertisements" in source
    assert "ends_on=(created_at AT TIME ZONE 'Asia/Kolkata')::date" in source


def test_store_can_delete_its_advertisement_card() -> None:
    source = Path("apps/api/wearo_api/store_advertisements.py").read_text()
    assert "DELETE FROM store_advertisements" in source
    assert "advertisement_id=:advertisement AND store_id=:store_id" in source


def test_advertisement_details_can_be_saved_without_regeneration() -> None:
    source = Path("apps/api/wearo_api/store_advertisements.py").read_text()
    assert "prompt=COALESCE(:prompt, prompt)" in source
    assert "self.generator.generate(clean_prompt)" not in source[source.index("    def update(") :]


def test_successful_ai_advertisement_generation_is_recorded_durably() -> None:
    source = Path("apps/api/wearo_api/store_advertisements.py").read_text()
    assert "INSERT INTO store_advertisement_generations" in source


def test_sponsored_quote_allowance_migration_accepts_business_limits() -> None:
    source = Path(
        "apps/api/migrations/versions/20261031_0057_sponsored_quote_allowance.py"
    ).read_text()
    assert 'down_revision: str | None = "20261031_0056"' in source
    assert "type_=sa.Integer()" in source
    assert "remaining_allowance IS NULL OR remaining_allowance >= 1" in source
