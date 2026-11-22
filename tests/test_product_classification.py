from apps.api.wearo_api.product_classification import ProductClassifier, ProductSignals


def test_unknown_is_used_when_no_reliable_product_evidence_exists() -> None:
    result = ProductClassifier().classify("JEWELLERY")

    assert result.category == "unknown"
    assert result.score is None
    assert result.evidence_sources == ()


def test_visual_jewellery_signals_are_classified() -> None:
    result = ProductClassifier().classify(
        "JEWELLERY",
        visual=ProductSignals(
            material="luxury",
            richness="luxury",
            stones="luxury",
            craftsmanship="premium",
        ),
    )

    assert result.category == "luxury"
    assert result.evidence_sources == ("AI_VISUAL",)


def test_trusted_metadata_and_price_override_the_same_visual_attributes() -> None:
    result = ProductClassifier().classify(
        "APPAREL",
        visual=ProductSignals(
            material="basic",
            richness="basic",
            stones="premium",
            craftsmanship="basic",
        ),
        merchant_attributes={
            "material": "pure silk",
            "richness": "heavily embellished",
            "craftsmanship": "couture",
            "brand_exclusivity": "bespoke exclusive",
        },
        price_minor=2_500_000,
        currency="INR",
    )

    assert result.category == "luxury"
    assert result.signals.material == "luxury"
    assert result.evidence_sources == ("AI_VISUAL", "MERCHANT_METADATA", "PRICE")


def test_unknown_currency_does_not_guess_a_price_tier() -> None:
    result = ProductClassifier().classify(
        "JEWELLERY",
        visual=ProductSignals(material="premium", richness="premium"),
        price_minor=999_999,
        currency="EUR",
    )

    assert result.category == "premium"
    assert "PRICE" not in result.evidence_sources


def test_exceptional_product_and_ultra_luxury_price_reach_top_tier() -> None:
    result = ProductClassifier().classify(
        "JEWELLERY",
        visual=ProductSignals(
            material="luxury",
            richness="luxury",
            stones="ultra_luxury",
            craftsmanship="luxury",
        ),
        merchant_attributes={"brand_exclusivity": "private commission"},
        price_minor=75_000_000,
        currency="INR",
    )

    assert result.category == "ultra_luxury"
