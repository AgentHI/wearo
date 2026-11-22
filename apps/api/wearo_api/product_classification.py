from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

ProductKind = Literal["APPAREL", "JEWELLERY"]
ProductCategory = Literal["unknown", "basic", "premium", "luxury", "ultra_luxury"]

CATEGORY_RANK: dict[ProductCategory, int] = {
    "unknown": 0,
    "basic": 1,
    "premium": 2,
    "luxury": 3,
    "ultra_luxury": 4,
}


@dataclass(frozen=True)
class ProductSignals:
    material: ProductCategory = "unknown"
    richness: ProductCategory = "unknown"
    stones: ProductCategory = "unknown"
    craftsmanship: ProductCategory = "unknown"
    brand_exclusivity: ProductCategory = "unknown"


@dataclass(frozen=True)
class ProductClassification:
    item_kind: ProductKind
    category: ProductCategory
    score: float | None
    signals: ProductSignals
    evidence_sources: tuple[str, ...] = ()
    price_minor: int | None = None
    currency: str | None = None

    def evidence(self) -> dict[str, object]:
        return {
            "score": self.score,
            "signals": {
                "material": self.signals.material,
                "richness": self.signals.richness,
                "stones": self.signals.stones,
                "craftsmanship": self.signals.craftsmanship,
                "brand_exclusivity": self.signals.brand_exclusivity,
            },
            "sources": list(self.evidence_sources),
            "price_minor": self.price_minor,
            "currency": self.currency,
        }


_SIGNAL_WEIGHTS = {
    "material": 0.20,
    "richness": 0.15,
    "stones": 0.15,
    "craftsmanship": 0.10,
    "brand_exclusivity": 0.10,
    "price": 0.30,
}

# Prices are minor currency units. These bands are deliberately explicit and can be
# revised independently of the scoring algorithm as merchandising policy changes.
_PRICE_BANDS: dict[tuple[ProductKind, str], tuple[int, int, int]] = {
    ("JEWELLERY", "INR"): (500_000, 5_000_000, 50_000_000),
    ("APPAREL", "INR"): (250_000, 1_500_000, 10_000_000),
    ("JEWELLERY", "USD"): (10_000, 100_000, 1_000_000),
    ("APPAREL", "USD"): (5_000, 30_000, 200_000),
}

_KEYWORDS: dict[str, dict[ProductCategory, tuple[str, ...]]] = {
    "material": {
        "basic": ("imitation", "costume", "base metal", "alloy", "polyester"),
        "premium": ("silver", "sterling", "cotton", "silk", "velvet", "linen"),
        "luxury": ("gold", "platinum", "couture fabric", "pure silk"),
        "ultra_luxury": ("rare platinum", "heritage textile", "museum grade"),
    },
    "richness": {
        "basic": ("small", "simple", "minimal", "lightweight"),
        "premium": ("medium", "embroidered", "embellished"),
        "luxury": ("heavy", "layered", "heavily embellished", "statement"),
        "ultra_luxury": ("high jewellery", "one of a kind", "museum piece"),
    },
    "stones": {
        "basic": ("none", "no stone", "plain"),
        "premium": ("synthetic", "bead", "sequin", "cubic zirconia", "cz"),
        "luxury": ("diamond", "ruby", "emerald", "sapphire", "precious"),
        "ultra_luxury": ("rare diamond", "uncut diamond", "exceptional gemstone"),
    },
    "craftsmanship": {
        "basic": ("basic", "machine-made", "machine made", "mass produced"),
        "premium": ("handcrafted", "handwoven", "handmade"),
        "luxury": ("intricate", "couture", "bespoke workmanship", "artisan"),
        "ultra_luxury": ("master artisan", "haute couture", "heritage craft"),
    },
    "brand_exclusivity": {
        "basic": ("unbranded", "mass market", "standard"),
        "premium": ("designer", "premium brand"),
        "luxury": ("custom", "limited edition", "bespoke", "exclusive"),
        "ultra_luxury": ("one-off", "one of one", "private commission", "iconic maison"),
    },
}


def _category(value: object) -> ProductCategory:
    normalized = str(value).strip().casefold()
    return normalized if normalized in CATEGORY_RANK else "unknown"


def _text(value: object) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value).casefold()
    return str(value).casefold()


def _metadata_signal(name: str, value: object) -> ProductCategory:
    direct = _category(value)
    if direct != "unknown":
        return direct
    normalized = _text(value)
    # Check higher tiers first so "heavily embellished" is not reduced to PREMIUM
    # merely because it also contains the word "embellished".
    for category in ("ultra_luxury", "luxury", "premium", "basic"):
        if any(keyword in normalized for keyword in _KEYWORDS[name][category]):
            return category
    return "unknown"


def _price_category(
    item_kind: ProductKind, price_minor: int | None, currency: str | None
) -> ProductCategory:
    if price_minor is None or price_minor < 0 or not currency:
        return "unknown"
    bands = _PRICE_BANDS.get((item_kind, currency.upper()))
    if bands is None:
        return "unknown"
    basic_ceiling, premium_ceiling, luxury_ceiling = bands
    if price_minor <= basic_ceiling:
        return "basic"
    if price_minor <= premium_ceiling:
        return "premium"
    if price_minor <= luxury_ceiling:
        return "luxury"
    return "ultra_luxury"


@dataclass(frozen=True)
class ProductClassifier:
    """Combine visual analysis with trusted merchant metadata and selling price."""

    weights: Mapping[str, float] = field(default_factory=lambda: dict(_SIGNAL_WEIGHTS))

    def classify(
        self,
        item_kind: ProductKind,
        *,
        visual: ProductSignals | None = None,
        merchant_attributes: Mapping[str, object] | None = None,
        price_minor: int | None = None,
        currency: str | None = None,
    ) -> ProductClassification:
        visual = visual or ProductSignals()
        attributes = merchant_attributes or {}
        resolved: dict[str, ProductCategory] = {}
        sources: set[str] = set()
        aliases = {
            "material": ("material",),
            "richness": ("richness", "size_richness", "size", "embellishment"),
            "stones": ("stones", "stone", "gemstones"),
            "craftsmanship": ("craftsmanship", "construction", "making"),
            "brand_exclusivity": ("brand_exclusivity", "brand", "exclusivity"),
        }
        for name, keys in aliases.items():
            merchant_value = next((attributes[key] for key in keys if key in attributes), None)
            merchant_category = (
                _metadata_signal(name, merchant_value)
                if merchant_value is not None
                else "unknown"
            )
            visual_category = getattr(visual, name)
            resolved[name] = (
                merchant_category if merchant_category != "unknown" else visual_category
            )
            if merchant_category != "unknown":
                sources.add("MERCHANT_METADATA")
            elif visual_category != "unknown":
                sources.add("AI_VISUAL")

        price_category = _price_category(item_kind, price_minor, currency)
        if price_category != "unknown":
            sources.add("PRICE")

        weighted_total = 0.0
        observed_weight = 0.0
        for name, observed_category in {**resolved, "price": price_category}.items():
            if observed_category == "unknown":
                continue
            weight = self.weights[name]
            weighted_total += CATEGORY_RANK[observed_category] * weight
            observed_weight += weight
        score = round(weighted_total / observed_weight, 3) if observed_weight else None
        if score is None:
            final_category: ProductCategory = "unknown"
        elif score < 1.67:
            final_category = "basic"
        elif score < 2.5:
            final_category = "premium"
        elif score < 3.25:
            final_category = "luxury"
        else:
            final_category = "ultra_luxury"
        return ProductClassification(
            item_kind=item_kind,
            category=final_category,
            score=score,
            signals=ProductSignals(**resolved),
            evidence_sources=tuple(sorted(sources)),
            price_minor=price_minor,
            currency=currency.upper() if currency else None,
        )
