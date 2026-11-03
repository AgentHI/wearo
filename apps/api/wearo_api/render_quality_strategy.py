from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class RenderQuality(StrEnum):
    """Provider-neutral image quality exposed by Wearo's backend contract."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class QualityStrategy(Protocol):
    def parameters(self, model: str, quality: RenderQuality) -> dict[str, str | int]: ...


class OpenAIQualityStrategy:
    _PORTRAIT_SIZES: dict[RenderQuality, str] = {
        RenderQuality.LOW: "832x1248",
        RenderQuality.MEDIUM: "1248x1872",
        RenderQuality.HIGH: "1664x2496",
    }

    def parameters(self, model: str, quality: RenderQuality) -> dict[str, str | int]:
        del model
        return {
            "quality": quality.value.casefold(),
            "size": self._PORTRAIT_SIZES[quality],
        }


class VertexTryOnQualityStrategy:
    def parameters(self, model: str, quality: RenderQuality) -> dict[str, str | int]:
        # virtual-try-on-001 preserves the input resolution and exposes no output-quality setting.
        del model, quality
        return {}


class BytePlusQualityStrategy:
    _SIZES: dict[RenderQuality, str] = {
        RenderQuality.LOW: "1K",
        RenderQuality.MEDIUM: "1.5K",
        RenderQuality.HIGH: "2K",
    }

    def parameters(self, model: str, quality: RenderQuality) -> dict[str, str | int]:
        del model
        return {"size": self._SIZES[quality]}


class BFLQualityStrategy:
    _RESOLUTIONS: dict[RenderQuality, str] = {
        RenderQuality.LOW: "1k",
        RenderQuality.MEDIUM: "1.5k",
        RenderQuality.HIGH: "2k",
    }

    def parameters(self, model: str, quality: RenderQuality) -> dict[str, str | int]:
        if "flux-3-image" in model.casefold():
            return {"resolution": self._RESOLUTIONS[quality]}
        # Older FLUX endpoints use explicit dimensions rather than named resolution tiers.
        width, height = {
            RenderQuality.LOW: (832, 1248),
            RenderQuality.MEDIUM: (1024, 1536),
            RenderQuality.HIGH: (1152, 1728),
        }[quality]
        return {"width": width, "height": height}


_STRATEGIES: dict[str, QualityStrategy] = {
    "OPENAI": OpenAIQualityStrategy(),
    "GOOGLE_VERTEX": VertexTryOnQualityStrategy(),
    "BYTEPLUS": BytePlusQualityStrategy(),
    "BFL": BFLQualityStrategy(),
    "BFLAI": BFLQualityStrategy(),
}


def quality_parameters(
    provider: str, model: str, quality: RenderQuality | str
) -> dict[str, str | int]:
    """Map Wearo quality to the request fields supported by a provider/model."""

    try:
        normalized_quality = (
            quality if isinstance(quality, RenderQuality) else RenderQuality(quality.upper())
        )
    except (AttributeError, ValueError):
        raise ValueError("quality must be LOW, MEDIUM, or HIGH") from None
    try:
        strategy = _STRATEGIES[provider.strip().upper()]
    except KeyError:
        raise ValueError(f"unsupported quality strategy provider: {provider}") from None
    return strategy.parameters(model, normalized_quality)
