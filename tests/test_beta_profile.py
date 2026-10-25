from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.beta_profile import (
    DailyQuotaService,
    DailyUsage,
    PersonProfile,
    PersonProfileService,
    ProfileError,
    ProfileImage,
    QuotaError,
)

NOW = datetime(2026, 10, 17, 20, tzinfo=UTC)


class MemoryProfileStore:
    def __init__(self) -> None:
        self.profiles: dict[UUID, PersonProfile] = {}

    def replace_active(self, profile: PersonProfile, replaced_at: datetime) -> None:
        self.profiles = {profile.account_id: profile}

    def active_for_account(self, account_id: UUID) -> PersonProfile | None:
        return self.profiles.get(account_id)

    def request_delete(self, profile_id: UUID, account_id: UUID, delete_after: datetime) -> bool:
        item = self.profiles.get(account_id)
        if item is None or item.profile_id != profile_id:
            return False
        self.profiles[account_id] = replace(item, status="DELETION_REQUESTED")
        return True

    def restore_requested(self, account_id: UUID, restored_at: datetime) -> bool:
        item = self.profiles.get(account_id)
        if item is None or item.status != "DELETION_REQUESTED":
            return False
        self.profiles[account_id] = replace(item, status="ACTIVE")
        return True


class MemoryQuotaStore:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, date], DailyUsage] = {}

    def get(self, account_id: UUID, usage_date: date) -> DailyUsage | None:
        return self.items.get((account_id, usage_date))

    def reserve(
        self, account_id: UUID, usage_date: date, job_id: UUID, maximum: int
    ) -> DailyUsage | None:
        item = self.get(account_id, usage_date) or DailyUsage(account_id, usage_date, 0, None)
        if item.active_job_id is not None or item.successful_generations >= maximum:
            return None
        item = replace(item, active_job_id=job_id)
        self.items[(account_id, usage_date)] = item
        return item

    def settle_success(
        self, account_id: UUID, usage_date: date, job_id: UUID, maximum: int
    ) -> DailyUsage | None:
        item = self.get(account_id, usage_date)
        if item is None or item.active_job_id != job_id or item.successful_generations >= maximum:
            return None
        item = replace(
            item, active_job_id=None, successful_generations=item.successful_generations + 1
        )
        self.items[(account_id, usage_date)] = item
        return item

    def release(self, account_id: UUID, usage_date: date, job_id: UUID) -> DailyUsage | None:
        item = self.get(account_id, usage_date)
        if item is None or item.active_job_id != job_id:
            return None
        item = replace(item, active_job_id=None)
        self.items[(account_id, usage_date)] = item
        return item


def profile(account_id: UUID) -> PersonProfile:
    return PersonProfile(
        uuid4(),
        account_id,
        uuid4(),
        uuid4(),
        uuid4(),
        Decimal("170"),
        Decimal("65"),
        "ACTIVE",
        None,
    )


def test_profile_is_reusable_owner_scoped_and_deletable() -> None:
    store = MemoryProfileStore()
    service = PersonProfileService(store)
    account = uuid4()
    item = profile(account)
    service.save(item, now=NOW)
    assert service.require(account) == item
    with pytest.raises(ProfileError):
        service.require(uuid4())
    service.delete(item.profile_id, account, now=NOW)
    with pytest.raises(ProfileError):
        service.require(account)

    assert service.restore_requested(account, now=NOW) is True
    assert service.require(account) == item
    assert service.restore_requested(account, now=NOW) is False


def test_profile_guidance_bounds_are_not_measurement_claims() -> None:
    service = PersonProfileService(MemoryProfileStore())
    item = profile(uuid4())
    with pytest.raises(ProfileError):
        service.save(replace(item, height_cm=Decimal("20")), now=NOW)
    with pytest.raises(ProfileError):
        service.save(replace(item, weight_kg=Decimal("500")), now=NOW)


def test_profile_supports_reusable_full_body_and_close_up_photos() -> None:
    store = MemoryProfileStore()
    service = PersonProfileService(store)
    item = profile(uuid4())
    full_body = ProfileImage(
        uuid4(), item.person_asset_id, item.consent_id, "FULL_BODY", "Full body", True
    )
    close_up = ProfileImage(uuid4(), uuid4(), uuid4(), "CLOSE_UP", "Close-up", False)
    item = replace(item, images=(full_body, close_up))

    service.save(item, now=NOW)

    assert service.require(item.account_id).image_for(close_up.asset_id) == close_up
    with pytest.raises(ProfileError):
        service.save(
            replace(item, images=(replace(full_body, is_primary=False), close_up)), now=NOW
        )


def test_profile_can_be_created_with_only_a_close_up_photo() -> None:
    store = MemoryProfileStore()
    service = PersonProfileService(store)
    item = profile(uuid4())
    close_up = ProfileImage(
        uuid4(), item.person_asset_id, item.consent_id, "CLOSE_UP", "Close-up", True
    )

    service.save(replace(item, images=(close_up,)), now=NOW)

    assert service.require(item.account_id).images == (close_up,)


def test_profile_rejects_other_photos_without_full_body_or_close_up() -> None:
    service = PersonProfileService(MemoryProfileStore())
    item = profile(uuid4())
    other = ProfileImage(uuid4(), item.person_asset_id, item.consent_id, "OTHER", "Other", True)

    with pytest.raises(ProfileError, match="full-body or close-up"):
        service.save(replace(item, images=(other,)), now=NOW)


def test_profile_supports_ten_photos_and_rejects_an_eleventh() -> None:
    service = PersonProfileService(MemoryProfileStore())
    item = profile(uuid4())
    full_body = ProfileImage(
        uuid4(), item.person_asset_id, item.consent_id, "FULL_BODY", "Full body", True
    )
    other_photos = tuple(
        ProfileImage(uuid4(), uuid4(), uuid4(), "OTHER", f"Photo {index}", False)
        for index in range(2, 11)
    )
    ten_photo_profile = replace(item, images=(full_body, *other_photos))

    service.save(ten_photo_profile, now=NOW)

    with pytest.raises(ProfileError, match="up to 10 photos"):
        service.save(
            replace(
                ten_photo_profile,
                images=(
                    *ten_photo_profile.images,
                    ProfileImage(uuid4(), uuid4(), uuid4(), "OTHER", "Photo 11", False),
                ),
            ),
            now=NOW,
        )


def test_only_successes_consume_three_per_ist_day_and_one_job_is_active() -> None:
    service = DailyQuotaService(MemoryQuotaStore())
    account = uuid4()
    for expected in (2, 1, 0):
        job = uuid4()
        service.reserve(account, job, now=NOW)
        with pytest.raises(QuotaError):
            service.reserve(account, uuid4(), now=NOW)
        service.settle_success(account, job, now=NOW)
        assert service.remaining(account, now=NOW) == expected
    with pytest.raises(QuotaError):
        service.reserve(account, uuid4(), now=NOW)


def test_failure_releases_slot_without_consuming_allowance() -> None:
    service = DailyQuotaService(MemoryQuotaStore())
    account, job = uuid4(), uuid4()
    service.reserve(account, job, now=NOW)
    service.release_failure(account, job, now=NOW)
    assert service.remaining(account, now=NOW) == 3
    assert DailyQuotaService.usage_date(NOW) == date(2026, 10, 18)


def test_disabled_daily_limit_always_reports_available_capacity() -> None:
    store = MemoryQuotaStore()
    service = DailyQuotaService(store, limit_enabled=False)
    account = uuid4()
    for _ in range(3):
        job = uuid4()
        store.reserve(account, service.usage_date(NOW), job, service.maximum)
        store.settle_success(account, service.usage_date(NOW), job, service.maximum)

    assert service.remaining(account, now=NOW) == 3
    assert service.limit_enabled is False
