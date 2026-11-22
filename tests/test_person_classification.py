from pathlib import Path

from apps.api.wearo_api.person_classification import (
    age_range_for_estimate,
    promoted_person_category,
)
from scripts.validate_migrations import validate_revision


def test_person_category_only_promotes_unknown_to_girl_to_woman() -> None:
    assert promoted_person_category("unknown", "girl") == "girl"
    assert promoted_person_category("girl", "woman") == "woman"
    assert promoted_person_category("woman", "girl") == "woman"
    assert promoted_person_category("woman", "unknown") == "woman"


def test_successful_try_on_records_a_person_instead_of_classifying_the_login() -> None:
    source = Path("apps/api/wearo_api/render_runtime.py").read_text()
    assert "INSERT INTO account_persons AS existing" in source
    assert "source_person_asset_id" in source
    assert "quote.product_kind IN ('APPAREL', 'JEWELLERY')" in source
    assert "UPDATE accounts AS account\n                    SET person_category" not in source


def test_duplicate_source_photo_fills_unknowns_without_overwriting_person_details() -> None:
    source = Path("apps/api/wearo_api/render_runtime.py").read_text()
    assert "ON CONFLICT (account_id, source_person_asset_id) DO UPDATE" in source
    assert "WHEN existing.person_category = 'unknown'" in source
    assert "WHEN existing.age_range = 'unknown'" in source
    assert "COALESCE(\n                              existing.estimated_age" in source
    assert "last_seen_at = EXCLUDED.last_seen_at" in source


def test_each_successful_try_on_keeps_its_b2b_store_observation() -> None:
    source = Path("apps/api/wearo_api/render_runtime.py").read_text()
    assert "INSERT INTO person_tryon_observations" in source
    assert "sponsored_session.store_id" in source
    assert "ON CONFLICT (render_job_id) DO NOTHING" in source
    assert "context.marketing_tenant_id = context.tenant_id" in source
    assert "business_account_id, store_id, marketing_eligible" in source


def test_estimated_age_maps_to_non_overlapping_analytics_ranges() -> None:
    assert age_range_for_estimate(9) == "under_10"
    assert age_range_for_estimate(10) == "10_19"
    assert age_range_for_estimate(20) == "20_29"
    assert age_range_for_estimate(39) == "30_39"
    assert age_range_for_estimate(60) == "60_plus"


def test_estimated_age_accepts_only_the_first_confident_successful_try_on() -> None:
    source = Path("apps/api/wearo_api/render_runtime.py").read_text()
    assert "estimated_age = COALESCE(" in source
    assert "existing.estimated_age, EXCLUDED.estimated_age" in source


def test_person_category_migration_is_valid() -> None:
    path = Path("apps/api/migrations/versions/20261122_0091_person_presentation_classification.py")
    assert validate_revision(path) == "20261122_0091"
    assert 'down_revision: str | None = "20261122_0090"' in path.read_text()


def test_age_range_migration_is_valid() -> None:
    path = Path("apps/api/migrations/versions/20261122_0092_person_age_range.py")
    assert validate_revision(path) == "20261122_0092"
    assert 'down_revision: str | None = "20261122_0091"' in path.read_text()


def test_estimated_age_migration_is_valid() -> None:
    path = Path("apps/api/migrations/versions/20261122_0093_person_estimated_age.py")
    assert validate_revision(path) == "20261122_0093"
    assert 'down_revision: str | None = "20261122_0092"' in path.read_text()


def test_account_person_directory_migration_is_valid_and_photo_deduplicated() -> None:
    path = Path("apps/api/migrations/versions/20261122_0094_account_person_directory.py")
    source = path.read_text()
    assert validate_revision(path) == "20261122_0094"
    assert 'down_revision: str | None = "20261122_0093"' in source
    assert '"account_id",\n            "source_person_asset_id"' in source
    assert 'name="uq_account_persons_source_asset"' in source
    assert 'sa.Column("marketing_eligible", sa.Boolean(), nullable=False' in source
    assert 'sa.Column("store_id", UUID)' in source


def test_optional_marketing_consent_migration_is_valid_and_store_scoped() -> None:
    path = Path("apps/api/migrations/versions/20261122_0097_optional_marketing_consent.py")
    source = path.read_text()
    assert validate_revision(path) == "20261122_0097"
    assert 'down_revision: str | None = "20261122_0096"' in source
    assert '"marketing_approved"' in source
    assert '"marketing_tenant_id"' in source
    assert '"person_tryon_observations"' in source


def test_platform_marketing_consent_migration_is_valid() -> None:
    path = Path("apps/api/migrations/versions/20261122_0098_platform_marketing_consent.py")
    source = path.read_text()
    assert validate_revision(path) == "20261122_0098"
    assert 'down_revision: str | None = "20261122_0097"' in source
    assert '"ck_consent_records_marketing_scope"' in source
    assert "op.drop_constraint" in source
