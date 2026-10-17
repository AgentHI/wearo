from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.beta_profile import PersonProfile
from apps.api.wearo_api.image_preflight import PreflightResult
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
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted

    def validate(self, person: bytes, item: bytes) -> PreflightResult:
        return PreflightResult(
            self.accepted,
            "ACCEPTED" if self.accepted else "ITEM_UNSUPPORTED",
            "ok" if self.accepted else "unsupported",
            item_kind="APPAREL",
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


class Quotes:
    def __init__(self) -> None:
        self.items: list[BetaRenderQuote] = []

    def create(self, quote: BetaRenderQuote) -> None:
        self.items.append(quote)


def setup(
    *, consent: bool = True, images: bool = True, remaining: int = 3, route: bool = True
) -> tuple[BetaRenderPreflightService, Quotes, UUID, UUID]:
    account, principal = uuid4(), uuid4()
    profile = PersonProfile(
        uuid4(), account, principal, uuid4(), uuid4(), Decimal("170"), None, "ACTIVE", None
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
    return service, quotes, account, principal


def test_valid_quote_captures_approved_route_allowance_and_limitation() -> None:
    service, quotes, account, principal = setup()
    result = service.quote(
        account_id=account,
        principal_id=principal,
        item_asset_id=uuid4(),
        person_image=b"p",
        item_image=b"i",
        now=NOW,
    )
    assert result.route.model == "virtual-try-on-001" and result.remaining_before == 3
    assert "not a sizing" in result.limitation and quotes.items == [result]


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ({"images": False}, "ITEM_UNSUPPORTED"),
        ({"remaining": 0}, "DAILY_LIMIT_REACHED"),
        ({"route": False}, "ROUTE_UNAVAILABLE"),
    ],
)
def test_invalid_prerequisites_create_no_quote(options: dict[str, object], code: str) -> None:
    service, quotes, account, principal = setup(**options)  # type: ignore[arg-type]
    with pytest.raises(RenderPreflightError) as error:
        service.quote(
            account_id=account,
            principal_id=principal,
            item_asset_id=uuid4(),
            person_image=b"p",
            item_image=b"i",
            now=NOW,
        )
    assert error.value.code == code and quotes.items == []
