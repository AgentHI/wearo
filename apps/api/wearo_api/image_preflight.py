from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal, Protocol

from PIL import Image, ImageStat, UnidentifiedImageError

ItemKind = Literal["APPAREL", "JEWELLERY", "AMBIGUOUS", "UNSUPPORTED"]


@dataclass(frozen=True)
class VisionAssessment:
    person_count: int
    full_body_visible: bool
    suspected_minor: bool
    safe_content: bool
    item_kind: ItemKind
    item_count: int


@dataclass(frozen=True)
class PreflightResult:
    accepted: bool
    code: str
    message: str
    width: int | None = None
    height: int | None = None
    item_kind: ItemKind | None = None


class VisionAnalyzer(Protocol):
    def assess(self, person_image: bytes, item_image: bytes) -> VisionAssessment: ...


class ImagePreflightService:
    def __init__(
        self,
        analyzer: VisionAnalyzer,
        *,
        max_bytes: int = 7 * 1024 * 1024,
        enforce_adult_only: bool = True,
        require_full_body: bool = True,
        allow_jewellery: bool = False,
    ) -> None:
        self.analyzer = analyzer
        self.max_bytes = max_bytes
        self.enforce_adult_only = enforce_adult_only
        self.require_full_body = require_full_body
        self.allow_jewellery = allow_jewellery

    def validate(self, person_image: bytes, item_image: bytes) -> PreflightResult:
        person = self._decode(person_image, "person")
        if isinstance(person, PreflightResult):
            return person
        item = self._decode(item_image, "item")
        if isinstance(item, PreflightResult):
            return item
        person_width, person_height, brightness = person
        if person_width < 512 or person_height < 512:
            return PreflightResult(
                False, "PERSON_TOO_SMALL", "Use a clearer photo at least 512 px wide and tall."
            )
        if brightness < 30 or brightness > 235:
            return PreflightResult(
                False, "PERSON_LIGHTING", "Retake the photo in even, natural lighting."
            )
        assessment = self.analyzer.assess(person_image, item_image)
        if not assessment.safe_content:
            return PreflightResult(False, "UNSAFE_CONTENT", "This image cannot be processed.")
        if self.enforce_adult_only and assessment.suspected_minor:
            return PreflightResult(False, "ADULT_ONLY", "The beta accepts adult profiles only.")
        if assessment.person_count != 1 or (
            self.require_full_body and not assessment.full_body_visible
        ):
            return PreflightResult(
                False, "PERSON_FRAMING", "Use one adult, fully visible in the frame."
            )
        contextual_jewellery = (
            self.allow_jewellery
            and assessment.item_kind == "JEWELLERY"
            and assessment.item_count >= 1
        )
        if assessment.item_kind == "AMBIGUOUS" or (
            assessment.item_count != 1 and not contextual_jewellery
        ):
            return PreflightResult(
                False,
                "ITEM_AMBIGUOUS",
                "Upload a photo with one identifiable primary wearable item.",
            )
        if assessment.item_kind == "JEWELLERY" and not self.allow_jewellery:
            return PreflightResult(
                False,
                "JEWELLERY_NOT_READY",
                "Jewellery generation is not yet supported.",
                item_kind="JEWELLERY",
            )
        if assessment.item_kind not in {"APPAREL", "JEWELLERY"}:
            return PreflightResult(
                False,
                "ITEM_UNSUPPORTED",
                "This wearable item is not supported yet.",
                item_kind=assessment.item_kind,
            )
        return PreflightResult(
            True,
            "ACCEPTED",
            "Ready to generate.",
            person_width,
            person_height,
            assessment.item_kind,
        )

    def _decode(self, content: bytes, label: str) -> tuple[int, int, float] | PreflightResult:
        if not content or len(content) > self.max_bytes:
            return PreflightResult(
                False, f"{label.upper()}_FILE", f"Upload a valid {label} image under 7 MB."
            )
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise UnidentifiedImageError
                width, height = image.size
                image.load()
                brightness = float(ImageStat.Stat(image.convert("L").resize((32, 32))).mean[0])
        except (UnidentifiedImageError, OSError, ValueError):
            return PreflightResult(
                False, f"{label.upper()}_FILE", f"Upload a valid JPEG, PNG, or WebP {label} image."
            )
        return width, height, brightness
