import io
from dataclasses import replace

from PIL import Image

from apps.api.wearo_api.image_preflight import ImagePreflightService, VisionAssessment


class FixedAnalyzer:
    def __init__(self, result: VisionAssessment) -> None:
        self.result = result

    def assess(self, person_image: bytes, item_image: bytes) -> VisionAssessment:
        return self.result


def image_bytes(level: int = 128, size: tuple[int, int] = (800, 1000)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, (level, level, level)).save(output, format="PNG")
    return output.getvalue()


def valid() -> VisionAssessment:
    return VisionAssessment(1, True, False, True, "APPAREL", 1)


def test_valid_apparel_input_passes() -> None:
    result = ImagePreflightService(FixedAnalyzer(valid())).validate(image_bytes(), image_bytes())
    assert result.accepted and result.item_kind == "APPAREL"


def test_invalid_file_size_and_lighting_fail_before_analyzer() -> None:
    service = ImagePreflightService(FixedAnalyzer(valid()))
    assert service.validate(b"not-image", image_bytes()).code == "PERSON_FILE"
    assert service.validate(image_bytes(0), image_bytes()).code == "PERSON_LIGHTING"
    assert service.validate(image_bytes(size=(200, 200)), image_bytes()).code == "PERSON_TOO_SMALL"


def test_adult_safety_and_framing_are_hard_stops() -> None:
    for assessment, code in (
        (replace(valid(), suspected_minor=True), "ADULT_ONLY"),
        (replace(valid(), safe_content=False), "UNSAFE_CONTENT"),
        (replace(valid(), person_count=2), "PERSON_FRAMING"),
    ):
        assert (
            ImagePreflightService(FixedAnalyzer(assessment))
            .validate(image_bytes(), image_bytes())
            .code
            == code
        )


def test_local_testing_accepts_close_up_and_jewellery_while_retaining_safety_checks() -> None:
    assessment = replace(
        valid(),
        suspected_minor=True,
        full_body_visible=False,
        item_kind="JEWELLERY",
        item_count=3,
    )

    result = ImagePreflightService(
        FixedAnalyzer(assessment),
        enforce_adult_only=False,
        require_full_body=False,
        allow_jewellery=True,
    ).validate(image_bytes(), image_bytes())

    assert result.accepted and result.item_kind == "JEWELLERY"

    unsafe = ImagePreflightService(
        FixedAnalyzer(replace(assessment, safe_content=False)),
        enforce_adult_only=False,
        require_full_body=False,
        allow_jewellery=True,
    ).validate(image_bytes(), image_bytes())
    assert not unsafe.accepted and unsafe.code == "UNSAFE_CONTENT"


def test_item_is_automatically_classified_and_unsupported_inputs_do_not_pass() -> None:
    cases = (
        (replace(valid(), item_kind="JEWELLERY"), "JEWELLERY_NOT_READY"),
        (replace(valid(), item_kind="AMBIGUOUS"), "ITEM_AMBIGUOUS"),
        (replace(valid(), item_kind="UNSUPPORTED"), "ITEM_UNSUPPORTED"),
        (replace(valid(), item_count=2), "ITEM_AMBIGUOUS"),
    )
    for assessment, code in cases:
        result = ImagePreflightService(FixedAnalyzer(assessment)).validate(
            image_bytes(), image_bytes()
        )
        assert not result.accepted and result.code == code
