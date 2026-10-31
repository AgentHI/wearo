from io import BytesIO
from pathlib import Path

from PIL import Image

from apps.api.wearo_api.store_advertisements import CARD_HEIGHT, CARD_WIDTH, crop_card


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
