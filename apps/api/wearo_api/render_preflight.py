from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from .beta_profile import PersonProfile, ProfileError
from .consent import ConsentError, ConsentPurpose
from .image_preflight import PreflightResult
from .person_classification import AgeRange, PersonCategory
from .product_classification import ProductCategory, ProductKind


class RenderPreflightError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str
    region: str
    capability: str
    enabled: bool


@dataclass(frozen=True)
class BetaRenderQuote:
    quote_id: UUID
    account_id: UUID
    principal_id: UUID
    profile_id: UUID
    person_asset_id: UUID
    consent_id: UUID
    item_asset_id: UUID
    route: ModelRoute
    remaining_before: int
    expires_at: datetime
    limitation: str
    product_kind: ProductKind | None = None
    product_category: ProductCategory = "unknown"
    classification_evidence: dict[str, object] | None = None
    person_category: PersonCategory = "unknown"
    age_range: AgeRange = "unknown"
    estimated_age: int | None = None


class RouteRegistry(Protocol):
    def route_for(self, capability: str, at: datetime) -> ModelRoute | None: ...


class QuoteStore(Protocol):
    def create(self, quote: BetaRenderQuote) -> None: ...


class ProfileReader(Protocol):
    def require(self, account_id: UUID) -> PersonProfile: ...


class ConsentReader(Protocol):
    def require_current(
        self,
        *,
        account_id: UUID,
        actor_principal_id: UUID,
        asset_id: UUID,
        purpose: ConsentPurpose,
    ) -> object: ...


class ImageValidator(Protocol):
    def validate(
        self,
        person_image: bytes,
        item_image: bytes,
        *,
        merchant_attributes: Mapping[str, object] | None = None,
        price_minor: int | None = None,
        currency: str | None = None,
    ) -> PreflightResult: ...


class QuotaReader(Protocol):
    def remaining(self, account_id: UUID, *, now: datetime) -> int: ...


class BetaRenderPreflightService:
    def __init__(
        self,
        profiles: ProfileReader,
        consents: ConsentReader,
        images: ImageValidator,
        quota: QuotaReader,
        routes: RouteRegistry,
        quotes: QuoteStore,
    ) -> None:
        self.profiles = profiles
        self.consents = consents
        self.images = images
        self.quota = quota
        self.routes = routes
        self.quotes = quotes

    def quote(
        self,
        *,
        account_id: UUID,
        principal_id: UUID,
        person_asset_id: UUID,
        item_asset_id: UUID,
        person_image: bytes,
        item_image: bytes,
        merchant_attributes: Mapping[str, object] | None = None,
        product_price_minor: int | None = None,
        product_currency: str | None = None,
        bypass_free_allowance: bool = False,
        sponsored_remaining: int | None = None,
        now: datetime | None = None,
    ) -> BetaRenderQuote:
        current = now or datetime.now(UTC)
        try:
            profile = self.profiles.require(account_id)
            if profile.principal_id != principal_id:
                raise ProfileError("active person profile is required")
            selected_image = profile.image_for(person_asset_id)
            if selected_image is None:
                raise ProfileError("selected photo is not part of the active profile")
            self.consents.require_current(
                account_id=account_id,
                actor_principal_id=principal_id,
                asset_id=selected_image.asset_id,
                purpose="TRY_ON",
            )
        except (ProfileError, ConsentError) as error:
            raise RenderPreflightError("PROFILE_OR_CONSENT_REQUIRED", str(error)) from None
        result = self.images.validate(
            person_image,
            item_image,
            merchant_attributes=merchant_attributes,
            price_minor=product_price_minor,
            currency=product_currency,
        )
        if not result.accepted:
            raise RenderPreflightError(result.code, result.message)
        remaining = (
            sponsored_remaining
            if bypass_free_allowance and sponsored_remaining is not None
            else self.quota.remaining(account_id, now=current)
        )
        if remaining < 1:
            raise RenderPreflightError(
                "SPONSORED_LIMIT_REACHED" if bypass_free_allowance else "FREE_TRYONS_USED",
                (
                    "No try-ons remain in this business-sponsored session."
                    if bypass_free_allowance
                    else "You have used all 3 free registration try-ons. "
                    "Buy more try-ons to continue."
                ),
            )
        route = self.routes.route_for("APPAREL", current)
        if route is None or not route.enabled:
            raise RenderPreflightError(
                "ROUTE_UNAVAILABLE", "Generation is temporarily unavailable."
            )
        quote = BetaRenderQuote(
            quote_id=uuid4(),
            account_id=account_id,
            principal_id=principal_id,
            profile_id=profile.profile_id,
            person_asset_id=selected_image.asset_id,
            consent_id=selected_image.consent_id,
            item_asset_id=item_asset_id,
            route=route,
            remaining_before=remaining,
            expires_at=current + timedelta(minutes=10),
            limitation="AI visual preview only; not a sizing, measurement, or fit guarantee.",
            product_kind=(
                result.product_classification.item_kind
                if result.product_classification is not None
                else None
            ),
            product_category=(
                result.product_classification.category
                if result.product_classification is not None
                else "unknown"
            ),
            classification_evidence=(
                result.product_classification.evidence()
                if result.product_classification is not None
                else None
            ),
            person_category=result.person_category,
            age_range=result.age_range,
            estimated_age=result.estimated_age,
        )
        self.quotes.create(quote)
        return quote
