from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class ProfileError(ValueError):
    pass


class QuotaError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileImage:
    profile_image_id: UUID
    asset_id: UUID
    consent_id: UUID
    photo_type: str
    label: str
    is_primary: bool


@dataclass(frozen=True)
class PersonProfile:
    profile_id: UUID
    account_id: UUID
    principal_id: UUID
    person_asset_id: UUID
    consent_id: UUID
    height_cm: Decimal | None
    weight_kg: Decimal | None
    status: str
    last_used_at: datetime | None
    images: tuple[ProfileImage, ...] = ()

    def image_for(self, asset_id: UUID) -> ProfileImage | None:
        for image in self.images:
            if image.asset_id == asset_id:
                return image
        if not self.images and self.person_asset_id == asset_id:
            return ProfileImage(
                profile_image_id=self.profile_id,
                asset_id=self.person_asset_id,
                consent_id=self.consent_id,
                photo_type="FULL_BODY",
                label="Full body",
                is_primary=True,
            )
        return None


@dataclass(frozen=True)
class DailyUsage:
    account_id: UUID
    usage_date_ist: date
    successful_generations: int
    active_job_id: UUID | None


class ProfileStore(Protocol):
    def replace_active(self, profile: PersonProfile, replaced_at: datetime) -> None: ...
    def active_for_account(self, account_id: UUID) -> PersonProfile | None: ...
    def request_delete(
        self, profile_id: UUID, account_id: UUID, delete_after: datetime
    ) -> bool: ...


class QuotaStore(Protocol):
    def reserve(
        self, account_id: UUID, usage_date: date, job_id: UUID, maximum: int
    ) -> DailyUsage | None: ...
    def settle_success(
        self, account_id: UUID, usage_date: date, job_id: UUID, maximum: int
    ) -> DailyUsage | None: ...
    def release(self, account_id: UUID, usage_date: date, job_id: UUID) -> DailyUsage | None: ...
    def get(self, account_id: UUID, usage_date: date) -> DailyUsage | None: ...


class PersonProfileService:
    def __init__(self, store: ProfileStore) -> None:
        self.store = store

    def save(self, profile: PersonProfile, *, now: datetime | None = None) -> None:
        if profile.status != "ACTIVE":
            raise ProfileError("profile must be active")
        if profile.height_cm is not None and not Decimal(80) <= profile.height_cm <= Decimal(260):
            raise ProfileError("height guidance is outside supported bounds")
        if profile.weight_kg is not None and not Decimal(20) <= profile.weight_kg <= Decimal(350):
            raise ProfileError("weight guidance is outside supported bounds")
        if profile.images:
            if len(profile.images) > 6:
                raise ProfileError("a profile supports up to six photos")
            if len({image.asset_id for image in profile.images}) != len(profile.images):
                raise ProfileError("profile photos must be unique")
            if len({image.photo_type for image in profile.images}) != len(profile.images):
                raise ProfileError("profile photo types must be unique")
            if any(
                image.photo_type not in {"FULL_BODY", "CLOSE_UP", "OTHER"}
                for image in profile.images
            ):
                raise ProfileError("unsupported profile photo type")
            if not any(image.photo_type == "FULL_BODY" for image in profile.images):
                raise ProfileError("profile requires a full-body photo")
            if sum(image.is_primary for image in profile.images) != 1:
                raise ProfileError("profile requires exactly one primary photo")
            primary = next(image for image in profile.images if image.is_primary)
            if primary.photo_type != "FULL_BODY":
                raise ProfileError("the full-body photo must be primary")
            if (primary.asset_id, primary.consent_id) != (
                profile.person_asset_id,
                profile.consent_id,
            ):
                raise ProfileError("primary profile photo is inconsistent")
        self.store.replace_active(profile, now or datetime.now(UTC))

    def require(self, account_id: UUID) -> PersonProfile:
        profile = self.store.active_for_account(account_id)
        if profile is None or profile.account_id != account_id or profile.status != "ACTIVE":
            raise ProfileError("active person profile is required")
        return profile

    def delete(self, profile_id: UUID, account_id: UUID, *, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        if not self.store.request_delete(profile_id, account_id, current + timedelta(hours=24)):
            raise ProfileError("active person profile is required")


class DailyQuotaService:
    maximum = 3

    def __init__(self, store: QuotaStore, *, limit_enabled: bool = True) -> None:
        self.store = store
        self.limit_enabled = limit_enabled

    @staticmethod
    def usage_date(now: datetime) -> date:
        return now.astimezone(IST).date()

    def remaining(self, account_id: UUID, *, now: datetime | None = None) -> int:
        if not self.limit_enabled:
            return self.maximum
        current = now or datetime.now(UTC)
        usage = self.store.get(account_id, self.usage_date(current))
        return self.maximum - (usage.successful_generations if usage else 0)

    def reserve(self, account_id: UUID, job_id: UUID, *, now: datetime | None = None) -> DailyUsage:
        current = now or datetime.now(UTC)
        result = self.store.reserve(account_id, self.usage_date(current), job_id, self.maximum)
        if result is None:
            raise QuotaError("daily allowance unavailable")
        return result

    def settle_success(
        self, account_id: UUID, job_id: UUID, *, now: datetime | None = None
    ) -> DailyUsage:
        current = now or datetime.now(UTC)
        result = self.store.settle_success(
            account_id, self.usage_date(current), job_id, self.maximum
        )
        if result is None:
            raise QuotaError("daily allowance unavailable")
        return result

    def release_failure(
        self, account_id: UUID, job_id: UUID, *, now: datetime | None = None
    ) -> DailyUsage:
        current = now or datetime.now(UTC)
        result = self.store.release(account_id, self.usage_date(current), job_id)
        if result is None:
            raise QuotaError("daily allowance unavailable")
        return result
