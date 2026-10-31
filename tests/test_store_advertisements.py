from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from apps.api.wearo_api.store_advertisements import (
    CARD_HEIGHT,
    CARD_WIDTH,
    StoreAdvertisementError,
    crop_card,
    validate_duration,
)


def test_uploaded_advertisement_is_cropped_to_bounded_tryon_card() -> None:
    source = BytesIO()
    Image.new("RGB", (1600, 600), "purple").save(source, "PNG")

    result = crop_card(source.getvalue())

    with Image.open(BytesIO(result)) as card:
        assert card.size == (CARD_WIDTH, CARD_HEIGHT)
        assert card.format == "JPEG"


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
