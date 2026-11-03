import pytest

from apps.api.wearo_api.render_quality_strategy import RenderQuality, quality_parameters


@pytest.mark.parametrize(
    ("quality", "expected"),
    [("LOW", "low"), ("MEDIUM", "medium"), ("HIGH", "high")],
)
def test_openai_maps_wearo_quality_to_provider_quality(quality: str, expected: str) -> None:
    parameters = quality_parameters("OPENAI", "gpt-image-2", quality)
    assert parameters["quality"] == expected


@pytest.mark.parametrize(
    ("provider", "model", "field", "values"),
    [
        ("BYTEPLUS", "dola-seedream-5-0-flash-260915", "size", ("1K", "1.5K", "2K")),
        ("BYTEPLUS", "custom-deployment-id", "size", ("1K", "1.5K", "2K")),
        ("BFL", "flux-3-image-klein", "resolution", ("1k", "1.5k", "2k")),
        (
            "OPENAI",
            "gpt-image-2",
            "size",
            ("832x1248", "1248x1872", "1664x2496"),
        ),
    ],
)
def test_provider_resolution_tiers(
    provider: str, model: str, field: str, values: tuple[str, str, str]
) -> None:
    actual = tuple(quality_parameters(provider, model, quality)[field] for quality in RenderQuality)
    assert actual == values


def test_legacy_bfl_models_use_explicit_portrait_dimensions() -> None:
    assert quality_parameters("BFLAI", "flux-2-klein-9b", "HIGH") == {
        "width": 1152,
        "height": 1728,
    }


def test_vertex_try_on_accepts_all_wearo_qualities_without_unsupported_fields() -> None:
    for quality in RenderQuality:
        assert quality_parameters("GOOGLE_VERTEX", "virtual-try-on-001", quality) == {}


def test_quality_strategy_rejects_unknown_quality_and_provider() -> None:
    with pytest.raises(ValueError, match="LOW, MEDIUM, or HIGH"):
        quality_parameters("OPENAI", "gpt-image-2", "ULTRA")
    with pytest.raises(ValueError, match="unsupported quality strategy provider"):
        quality_parameters("UNKNOWN", "model", "HIGH")
