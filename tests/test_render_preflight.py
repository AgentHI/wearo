from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.beta_profile import PersonProfile
from apps.api.wearo_api.image_preflight import PreflightResult
from apps.api.wearo_api.product_classification import ProductClassifier, ProductSignals
from apps.api.wearo_api.render_preflight import (
    BetaRenderPreflightService,
    BetaRenderQuote,
    ModelRoute,
    RenderPreflightError,
)

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class Profiles:
    def __init__(self, item: PersonProfile | None) -> None:
        self.item = item

    def require(self, account_id: UUID) -> PersonProfile:
        if self.item is None or self.item.account_id != account_id:
            raise ValueError("missing")
        return self.item


class Consents:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def require_current(self, **kwargs: object) -> object:
        if not self.allowed:
            raise ValueError("missing")
        return object()


class Images:
    def __init__(self, accepted: bool = True, *, high_jewellery: bool = False) -> None:
        self.accepted = accepted
        self.high_jewellery = high_jewellery

    def validate(
        self,
        person: bytes,
        item: bytes,
        *,
        merchant_attributes: Mapping[str, object] | None = None,
        price_minor: int | None = None,
        currency: str | None = None,
    ) -> PreflightResult:
        classification = (
            ProductClassifier().classify(
                "JEWELLERY",
                visual=ProductSignals(
                    material="luxury",
                    richness="luxury",
                    stones="luxury",
                    craftsmanship="luxury",
                ),
            )
            if self.high_jewellery
            else None
        )
        return PreflightResult(
            self.accepted,
            "ACCEPTED" if self.accepted else "ITEM_UNSUPPORTED",
            "ok" if self.accepted else "unsupported",
            item_kind="JEWELLERY" if self.high_jewellery else "APPAREL",
            product_classification=classification,
            person_category="woman",
            age_range="30_39",
            estimated_age=34,
        )


class Quota:
    def __init__(self, remaining: int = 3) -> None:
        self.value = remaining

    def remaining(self, account_id: UUID, *, now: datetime) -> int:
        return self.value


class Routes:
    def __init__(self, enabled: bool = True) -> None:
        self.route = ModelRoute(
            "GOOGLE_VERTEX", "virtual-try-on-001", "asia-southeast1", "APPAREL", enabled
        )

    def route_for(self, capability: str, at: datetime) -> ModelRoute | None:
        return self.route

    def routes_for(self, capability: str, at: datetime) -> tuple[ModelRoute, ...]:
        return (self.route,)


class Quotes:
    def __init__(self) -> None:
        self.items: list[BetaRenderQuote] = []

    def create(self, quote: BetaRenderQuote) -> None:
        self.items.append(quote)


def setup(
    *, consent: bool = True, images: bool = True, remaining: int = 3, route: bool = True
) -> tuple[BetaRenderPreflightService, Quotes, UUID, UUID, UUID]:
    account, principal = uuid4(), uuid4()
    person_asset_id = uuid4()
    profile = PersonProfile(
        uuid4(),
        account,
        principal,
        person_asset_id,
        uuid4(),
        Decimal("170"),
        None,
        "ACTIVE",
        None,
    )
    quotes = Quotes()
    service = BetaRenderPreflightService(
        Profiles(profile),
        Consents(consent),
        Images(images),
        Quota(remaining),
        Routes(route),
        quotes,
    )
    return service, quotes, account, principal, person_asset_id


def test_valid_quote_captures_approved_route_allowance_and_limitation() -> None:
    service, quotes, account, principal, person_asset_id = setup()
    result = service.quote(
        account_id=account,
        principal_id=principal,
        person_asset_id=person_asset_id,
        item_asset_id=uuid4(),
        person_image=b"p",
        item_image=b"i",
        now=NOW,
    )
    assert result.route.model == "virtual-try-on-001" and result.remaining_before == 3
    assert "not a sizing" in result.limitation and quotes.items == [result]


def test_quote_snapshots_routes_in_priority_order() -> None:
    service, _quotes, account, principal, person_asset_id = setup()
    primary = ModelRoute("BYTEPLUS", "model-a", "ap-southeast-1", "APPAREL", True, 1)
    fallback = ModelRoute("BFL", "model-b", "global", "APPAREL", True, 2)

    class PriorityRoutes:
        def route_for(self, capability: str, at: datetime) -> ModelRoute | None:
            return primary

        def routes_for(self, capability: str, at: datetime) -> tuple[ModelRoute, ...]:
            return (primary, fallback)

    service.routes = PriorityRoutes()
    result = service.quote(
        account_id=account,
        principal_id=principal,
        person_asset_id=person_asset_id,
        item_asset_id=uuid4(),
        person_image=b"p",
        item_image=b"i",
        now=NOW,
    )

    assert result.route_candidates == (primary, fallback)


def test_quote_captures_product_category_for_successful_render_settlement() -> None:
    service, quotes, account, principal, person_asset_id = setup()
    service.images = Images(high_jewellery=True)

    result = service.quote(
        account_id=account,
        principal_id=principal,
        person_asset_id=person_asset_id,
        item_asset_id=uuid4(),
        person_image=b"p",
        item_image=b"i",
        now=NOW,
    )

    assert result.product_kind == "JEWELLERY"
    assert result.product_category == "luxury"
    assert result.classification_evidence is not None
    assert result.person_category == "woman"
    assert result.age_range == "30_39"
    assert result.estimated_age == 34


def test_sponsored_quote_uses_business_allowance_when_personal_quota_is_used() -> None:
    service, quotes, account, principal, person_asset_id = setup(remaining=0)
    result = service.quote(
        account_id=account,
        principal_id=principal,
        person_asset_id=person_asset_id,
        item_asset_id=uuid4(),
        person_image=b"p",
        item_image=b"i",
        bypass_free_allowance=True,
        sponsored_remaining=2,
        now=NOW,
    )

    assert result.remaining_before == 2
    assert quotes.items == [result]


def test_purchased_tryons_extend_personal_allowance_after_free_grant_is_used() -> None:
    service, quotes, account, principal, person_asset_id = setup(remaining=0)
    result = service.quote(
        account_id=account,
        principal_id=principal,
        person_asset_id=person_asset_id,
        item_asset_id=uuid4(),
        person_image=b"p",
        item_image=b"i",
        purchased_remaining=13,
        now=NOW,
    )

    assert result.remaining_before == 13
    assert quotes.items == [result]


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ({"images": False}, "ITEM_UNSUPPORTED"),
        ({"remaining": 0}, "FREE_TRYONS_USED"),
        ({"route": False}, "ROUTE_UNAVAILABLE"),
    ],
)
def test_invalid_prerequisites_create_no_quote(options: dict[str, object], code: str) -> None:
    service, quotes, account, principal, person_asset_id = setup(**options)  # type: ignore[arg-type]
    with pytest.raises(RenderPreflightError) as error:
        service.quote(
            account_id=account,
            principal_id=principal,
            person_asset_id=person_asset_id,
            item_asset_id=uuid4(),
            person_image=b"p",
            item_image=b"i",
            now=NOW,
        )
    assert error.value.code == code and quotes.items == []


def test_quote_rejects_photo_outside_active_profile() -> None:
    service, quotes, account, principal, _person_asset_id = setup()

    with pytest.raises(RenderPreflightError) as error:
        service.quote(
            account_id=account,
            principal_id=principal,
            person_asset_id=uuid4(),
            item_asset_id=uuid4(),
            person_image=b"p",
            item_image=b"i",
            now=NOW,
        )

    assert error.value.code == "PROFILE_OR_CONSENT_REQUIRED"
    assert quotes.items == []
