import base64
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast
from uuid import uuid4

import pytest
import requests
from PIL import Image, ImageDraw
from pytest import MonkeyPatch

from apps.api.wearo_api.render_provider import (
    APPAREL_ACCESSORY_NEGATIVE_PROMPT,
    APPAREL_ACCESSORY_PRESERVATION_PROMPT,
    PERSON_PRESERVATION_NEGATIVE_PROMPT,
    PERSON_PRESERVATION_PROMPT,
)
from apps.cost_lab_api.adapters import (
    BFLAdapter,
    BFLUpstreamError,
    BytePlusAdapter,
    RunwareAdapter,
    normalize_openai_usage,
)
from apps.cost_lab_api.app import (
    _RUNWARE_EARRINGS_ONLY_NEGATIVE_PROMPT,
    _RUNWARE_EARRINGS_ONLY_PROMPT,
    _RUNWARE_JEWELLERY_NEGATIVE_PROMPT,
    _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT,
    _RUNWARE_NECKLACE_ONLY_PROMPT,
    _RUNWARE_SPLIT_JEWELLERY_NEGATIVE_PROMPT,
    _RUNWARE_SPLIT_JEWELLERY_PROMPT,
    _benchmark_category_instruction,
    _benchmark_prompt,
    _populate_result_image_fields,
    reproducible_combinations,
)
from apps.cost_lab_api.jewellery_references import (
    plan_runware_jewellery_references,
    runware_jewellery_reference_images,
    split_lower_earring_reference,
)
from apps.cost_lab_api.pricing import calculate_cost, normalized_total_tokens
from workers.cost_lab_worker.main import _prepare_tryon_generation


def test_cost_lab_pricing_supports_disjoint_units() -> None:
    usage = {"text_input_tokens": 1_000_000, "image_output_tokens": 500_000, "requests": 2}
    prices = [
        {"unit": "text_input_tokens", "price_usd": "2"},
        {"unit": "image_output_tokens", "price_usd": "8"},
        {"unit": "requests", "price_usd": "0.25"},
    ]
    assert calculate_cost(usage, prices) == Decimal("6.50000000")


def test_result_detail_uses_saved_image_metadata_without_storage_read() -> None:
    class UnexpectedStorage:
        def get(self, _key: str) -> bytes:
            raise AssertionError("stored metadata should avoid an S3 read")

    tryon_id = uuid4()
    item = {
        "tryon_id": tryon_id,
        "output_path": f"benchmarks/run/{tryon_id}.png",
        "raw_metadata": {
            "pixel_width": 1024,
            "pixel_height": 1024,
            "image_format": "PNG",
            "file_size_bytes": 123_456,
        },
    }

    _populate_result_image_fields(SimpleNamespace(storage=UnexpectedStorage()), item)

    assert item["pixel_width"] == 1024
    assert item["pixel_height"] == 1024
    assert item["image_format"] == "PNG"
    assert item["file_size_bytes"] == 123_456
    assert item["image_url"] == f"/api/cost-lab/results/tryons/{tryon_id}/image"
    assert item["download_url"].endswith("?download=true")


def test_result_detail_storage_timeout_does_not_hide_image_links() -> None:
    class TimeoutStorage:
        def get(self, _key: str) -> bytes:
            raise TimeoutError("S3 read timed out")

    tryon_id = uuid4()
    item = {
        "tryon_id": tryon_id,
        "output_path": f"benchmarks/run/{tryon_id}.png",
        "raw_metadata": {},
    }

    _populate_result_image_fields(SimpleNamespace(storage=TimeoutStorage()), item)

    assert item["image_url"] == f"/api/cost-lab/results/tryons/{tryon_id}/image"
    assert item["download_url"].endswith("?download=true")
    assert item["pixel_width"] is None
    assert item["pixel_height"] is None
    assert item["image_format"] is None
    assert item["file_size_bytes"] is None


def test_result_detail_keeps_metadata_for_legacy_results() -> None:
    output = BytesIO()
    Image.new("RGB", (37, 29), (10, 20, 30)).save(output, "PNG")
    content = output.getvalue()

    class LegacyStorage:
        def get(self, _key: str) -> bytes:
            return content

    tryon_id = uuid4()
    item = {
        "tryon_id": tryon_id,
        "output_path": f"benchmarks/run/{tryon_id}.png",
        "raw_metadata": {},
    }

    _populate_result_image_fields(SimpleNamespace(storage=LegacyStorage()), item)

    assert item["pixel_width"] == 37
    assert item["pixel_height"] == 29
    assert item["image_format"] == "PNG"
    assert item["file_size_bytes"] == len(content)


def test_cost_lab_aggregate_tokens_are_not_double_counted() -> None:
    usage = {"text_input_tokens": 10, "image_input_tokens": 20, "total_reported_tokens": 99}
    assert normalized_total_tokens(usage) == 99
    assert calculate_cost(usage, [{"unit": "text_input_tokens", "price_usd": 1}]) == Decimal(
        "0.00001000"
    )


def test_cost_lab_combinations_are_reproducible_and_quality_scoped() -> None:
    people = [{"asset_id": uuid4()} for _ in range(3)]
    products = [{"asset_id": uuid4()} for _ in range(4)]
    first = reproducible_combinations(people, products, ["LOW", "HIGH"], 10, 4821)
    second = reproducible_combinations(people, products, ["LOW", "HIGH"], 10, 4821)
    assert first == second
    assert len(first) == 20
    assert [quality for quality, _, _ in first].count("LOW") == 10


def test_jewellery_benchmark_prompt_replaces_existing_set_and_wears_earrings() -> None:
    prompt = _benchmark_prompt("JEWELLERY")

    assert "remove all jewellery originally worn" in prompt
    assert "product inventory, not a scene" in prompt
    assert "Every smaller jewellery piece physically disconnected" in prompt
    assert "even when it is displayed directly below the necklace" in prompt
    assert "FINAL PLACEMENT CONTRACT" in prompt
    assert "exactly two matching earrings" in prompt
    assert "one attached to the left earlobe" in prompt
    assert "one attached to the right earlobe" in prompt
    assert "If IMAGE 2 shows only one earring, use its design for both ears" in prompt
    assert "CONSUME, DO NOT COPY" in prompt
    assert "not allowed to contain the source pair below the necklace" in prompt
    assert "zero earrings on the chest or clothing" in prompt
    assert "Apart from using one visible earring design for the required matching pair" in prompt
    assert "Do not recolour, redesign, simplify, duplicate" not in prompt
    assert len(prompt) < 4_000


def test_benchmark_prompt_does_not_invent_spectacles() -> None:
    prompt = _benchmark_prompt("JEWELLERY")

    assert "introduce no new accessory" in prompt
    assert "bare eyes without spectacles" in prompt
    assert "never add eyeglasses, lenses, rims, or frames" in prompt
    assert "If eyewear is genuinely present" in prompt


def test_cost_lab_runware_tryon_uses_person_lock_and_input_aspect_ratio() -> None:
    person = Image.new("RGB", (1152, 2048), "white")
    encoded = BytesIO()
    person.save(encoded, format="JPEG")
    jewellery_prompt = _benchmark_prompt("JEWELLERY")

    prompt, parameters = _prepare_tryon_generation(
        jewellery_prompt,
        {"width": 1536, "height": 1536, "negativePrompt": "existing exclusions"},
        encoded.getvalue(),
        is_runware=True,
        is_apparel=False,
    )

    assert prompt.startswith(PERSON_PRESERVATION_PROMPT)
    assert jewellery_prompt in prompt
    assert parameters["width"] == 1152
    assert parameters["height"] == 2048
    assert parameters["negativePrompt"].startswith(PERSON_PRESERVATION_NEGATIVE_PROMPT)
    assert parameters["negativePrompt"].endswith("existing exclusions")

    apparel_prompt, apparel_parameters = _prepare_tryon_generation(
        _benchmark_prompt("DRESS"),
        {"width": 1536, "height": 1536},
        encoded.getvalue(),
        is_runware=True,
        is_apparel=True,
    )
    assert APPAREL_ACCESSORY_PRESERVATION_PROMPT in apparel_prompt
    assert APPAREL_ACCESSORY_NEGATIVE_PROMPT in apparel_parameters["negativePrompt"]


def test_runware_jewellery_negative_prompt_forbids_displayed_earrings() -> None:
    assert "original earrings" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "earrings on chest" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "earrings below necklace" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "product earrings copied to chest" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "loose earrings" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "extra earrings beyond one pair" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "single worn earring" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "one bare ear" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT
    assert "earring used as pendant" in _RUNWARE_JEWELLERY_NEGATIVE_PROMPT


def test_runware_split_jewellery_prompt_assigns_each_reference_one_role() -> None:
    assert "REFERENCE IMAGE 2 contains only the new necklace" in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    assert (
        "REFERENCE IMAGE 3 contains one isolated earring design"
        in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    )
    assert "exactly one supplied necklace" in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    assert "exactly two supplied earrings" in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    assert "literal design blueprint" in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    assert "every gemstone's exact colour, count, cut, shape" in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    assert "Derive the necklace only from REFERENCE IMAGE 2" in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    assert "Never transfer an earring detail onto the necklace" in _RUNWARE_SPLIT_JEWELLERY_PROMPT
    assert "earring below necklace" in _RUNWARE_SPLIT_JEWELLERY_NEGATIVE_PROMPT
    assert "bare neck" in _RUNWARE_SPLIT_JEWELLERY_NEGATIVE_PROMPT
    assert "wrong stone colour" in _RUNWARE_SPLIT_JEWELLERY_NEGATIVE_PROMPT
    assert "altered stone placement" in _RUNWARE_SPLIT_JEWELLERY_NEGATIVE_PROMPT


def test_runware_necklace_only_prompt_requires_no_earrings() -> None:
    assert (
        "REFERENCE IMAGE 2 contains one necklace and no earrings"
        in _RUNWARE_NECKLACE_ONLY_PROMPT
    )
    assert "exactly one supplied necklace" in _RUNWARE_NECKLACE_ONLY_PROMPT
    assert "zero earrings" in _RUNWARE_NECKLACE_ONLY_PROMPT
    assert "literal design blueprint" in _RUNWARE_NECKLACE_ONLY_PROMPT
    assert "exact metal colour, chain-link pattern" in _RUNWARE_NECKLACE_ONLY_PROMPT
    assert "bare neck" in _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT
    assert "earrings" in _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT
    assert "changed chain links" in _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT


def test_runware_earrings_only_prompt_requires_a_pair_and_no_necklace() -> None:
    assert "one isolated earring design and no necklace" in _RUNWARE_EARRINGS_ONLY_PROMPT
    assert "exactly one to the left earlobe" in _RUNWARE_EARRINGS_ONLY_PROMPT
    assert "exactly one to the right earlobe" in _RUNWARE_EARRINGS_ONLY_PROMPT
    assert "bare neck with zero necklaces" in _RUNWARE_EARRINGS_ONLY_PROMPT
    assert "literal design blueprint" in _RUNWARE_EARRINGS_ONLY_PROMPT
    assert "Do not recolour, swap, add, remove" in _RUNWARE_EARRINGS_ONLY_PROMPT
    assert "necklace" in _RUNWARE_EARRINGS_ONLY_NEGATIVE_PROMPT
    assert "single earring" in _RUNWARE_EARRINGS_ONLY_NEGATIVE_PROMPT
    assert "changed earring design" in _RUNWARE_EARRINGS_ONLY_NEGATIVE_PROMPT


def _catalogue_jewellery_image(*, earrings: bool = True) -> bytes:
    image = Image.new("RGB", (320, 320), (242, 230, 207))
    drawing = ImageDraw.Draw(image)
    gold = (185, 118, 20)
    drawing.arc((38, 25, 282, 180), 180, 360, fill=gold, width=10)
    drawing.line((38, 102, 138, 150, 182, 150, 282, 102), fill=gold, width=10)
    drawing.ellipse((137, 130, 183, 176), fill=(20, 125, 70), outline=gold, width=6)
    if earrings:
        for centre in (88, 232):
            drawing.ellipse(
                (centre - 13, 218, centre + 13, 244),
                fill=(20, 125, 70),
                outline=gold,
                width=5,
            )
            drawing.line((centre, 244, centre, 268), fill=gold, width=6)
            drawing.ellipse(
                (centre - 12, 260, centre + 12, 286),
                fill=(90, 35, 135),
                outline=gold,
                width=5,
            )
    output = BytesIO()
    image.save(output, "JPEG", quality=96)
    return output.getvalue()


def _catalogue_earrings_image(*, count: int = 2) -> bytes:
    image = Image.new("RGB", (320, 320), (242, 230, 207))
    drawing = ImageDraw.Draw(image)
    gold = (185, 118, 20)
    centres = (160,) if count == 1 else (105, 215)
    for centre in centres:
        drawing.ellipse(
            (centre - 17, 105, centre + 17, 139),
            fill=(20, 125, 70),
            outline=gold,
            width=5,
        )
        drawing.line((centre, 139, centre, 185), fill=gold, width=7)
        drawing.ellipse(
            (centre - 18, 175, centre + 18, 218),
            fill=(90, 35, 135),
            outline=gold,
            width=5,
        )
    output = BytesIO()
    image.save(output, "JPEG", quality=96)
    return output.getvalue()


def _catalogue_near_square_necklace_set() -> bytes:
    """Model a deep U-shaped necklace whose bounding box is not wider than it is tall."""

    image = Image.new("RGB", (320, 320), (242, 230, 207))
    drawing = ImageDraw.Draw(image)
    gold = (185, 118, 20)
    drawing.ellipse((42, 12, 278, 252), outline=gold, width=10)
    drawing.ellipse((140, 215, 180, 257), fill=(20, 125, 70), outline=gold, width=5)
    for centre in (82, 238):
        drawing.ellipse(
            (centre - 12, 270, centre + 12, 294),
            fill=(20, 125, 70),
            outline=gold,
            width=5,
        )
        drawing.line((centre, 294, centre, 312), fill=gold, width=5)
    output = BytesIO()
    image.save(output, "JPEG", quality=96)
    return output.getvalue()


def _catalogue_side_earrings_with_label() -> bytes:
    image = Image.new("RGB", (400, 400), (242, 230, 207))
    drawing = ImageDraw.Draw(image)
    gold = (185, 118, 20)
    drawing.ellipse((25, 18, 300, 315), outline=gold, width=10)
    drawing.ellipse((135, 265, 190, 320), fill=(20, 125, 70), outline=gold, width=6)
    for centre in (330, 370):
        drawing.ellipse(
            (centre - 13, 145, centre + 13, 171),
            fill=(150, 20, 55),
            outline=gold,
            width=5,
        )
        drawing.ellipse(
            (centre - 16, 170, centre + 16, 217),
            fill=(20, 125, 70),
            outline=gold,
            width=5,
        )
    drawing.line((343, 202, 357, 202), fill=(160, 145, 125), width=3)
    drawing.rectangle((22, 350, 160, 382), outline=(90, 80, 70), width=3)
    drawing.line((42, 363, 140, 363), fill=(90, 80, 70), width=4)
    output = BytesIO()
    image.save(output, "JPEG", quality=96)
    return output.getvalue()


def test_catalogue_jewellery_reference_is_split_before_one_runware_call() -> None:
    product = _catalogue_jewellery_image()
    split = split_lower_earring_reference(product)

    assert split is not None
    plan = plan_runware_jewellery_references(b"person", product)
    assert plan.strategy == "person_necklace_earring"
    references = runware_jewellery_reference_images(b"person", product)
    assert len(references) == 3
    assert references[0] == b"person"
    with Image.open(BytesIO(split.necklace_image)) as necklace:
        assert max(abs(channel - background) for channel, background in zip(
            necklace.getpixel((88, 250)), (242, 230, 207), strict=True
        )) < 20
        assert necklace.getpixel((160, 150))[1] > necklace.getpixel((160, 150))[0]
    with Image.open(BytesIO(split.earring_image)) as earring:
        rgb = earring.convert("RGB")
        assert any(
            green > red + 30
            for y in range(rgb.height)
            for x in range(rgb.width)
            for red, green, _blue in [rgb.getpixel((x, y))]
        )


def test_necklace_without_detached_earrings_keeps_combined_reference() -> None:
    product = _catalogue_jewellery_image(earrings=False)
    assert split_lower_earring_reference(product) is None
    plan = plan_runware_jewellery_references(b"person", product)
    assert plan.strategy == "person_necklace"
    assert runware_jewellery_reference_images(b"person", product) == [b"person", product]


def test_near_square_necklace_with_detached_earrings_is_a_combined_set() -> None:
    product = _catalogue_near_square_necklace_set()
    plan = plan_runware_jewellery_references(b"person", product)

    assert plan.strategy == "person_necklace_earring"
    assert len(plan.images) == 3


def test_side_earrings_are_extracted_instead_of_catalogue_label() -> None:
    product = _catalogue_side_earrings_with_label()
    plan = plan_runware_jewellery_references(b"person", product)

    assert plan.strategy == "person_necklace_earring"
    assert len(plan.images) == 3
    with Image.open(BytesIO(plan.images[1])) as necklace:
        rgb = necklace.convert("RGB")
        assert max(
            abs(channel - background)
            for channel, background in zip(
                rgb.getpixel((330, 180)), (242, 230, 207), strict=True
            )
        ) < 25
    with Image.open(BytesIO(plan.images[2])) as earring:
        rgb = earring.convert("RGB")
        assert any(
            green > red + 30
            for y in range(rgb.height)
            for x in range(rgb.width)
            for red, green, _blue in [rgb.getpixel((x, y))]
        )


@pytest.mark.parametrize("count", [1, 2])
def test_earrings_only_reference_uses_one_isolated_earring(count: int) -> None:
    product = _catalogue_earrings_image(count=count)
    plan = plan_runware_jewellery_references(b"person", product)

    assert plan.strategy == "person_earring"
    assert len(plan.images) == 2
    assert plan.images[0] == b"person"
    with Image.open(BytesIO(plan.images[1])) as earring:
        rgb = earring.convert("RGB")
        assert any(
            green > red + 30
            for y in range(rgb.height)
            for x in range(rgb.width)
            for red, green, _blue in [rgb.getpixel((x, y))]
        )


@pytest.mark.parametrize("category", ["SAREE", "DRESS"])
def test_apparel_benchmark_prompt_preserves_existing_jewellery(category: str) -> None:
    typed_category = cast(Literal["SAREE", "DRESS"], category)
    prompt = _benchmark_category_instruction(typed_category)

    assert "PRESERVE EXISTING JEWELLERY" in prompt
    assert "retain every jewellery item already worn" in prompt
    assert "Do not remove, replace, recolour" in prompt
    assert "remove every jewellery item currently worn" not in prompt


def test_benchmark_accepts_multiple_unique_product_sources() -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import BenchmarkBody

    products = [uuid4(), uuid4()]
    body = BenchmarkBody.model_validate({
        "model_id": str(uuid4()), "category": "DRESS",
        "product_asset_ids": [str(item) for item in products],
    })
    assert body.product_asset_ids == products
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkBody.model_validate({
            "model_id": str(uuid4()), "category": "DRESS",
            "product_asset_ids": [str(products[0]), str(products[0])],
        })


def test_production_model_priorities_must_be_unique_and_between_one_and_twenty() -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import ProductionModelPrioritiesBody

    releases = [uuid4(), uuid4()]
    body = ProductionModelPrioritiesBody.model_validate({"priorities": [
        {"release_id": str(releases[0]), "priority": 2},
        {"release_id": str(releases[1]), "priority": 1},
    ]})
    assert [item.priority for item in body.priorities] == [2, 1]

    with pytest.raises(ValidationError, match="unique"):
        ProductionModelPrioritiesBody.model_validate({"priorities": [
            {"release_id": str(releases[0]), "priority": 1},
            {"release_id": str(releases[1]), "priority": 1},
        ]})
    with pytest.raises(ValidationError, match="less than or equal to 20"):
        ProductionModelPrioritiesBody.model_validate({"priorities": [
            {"release_id": str(releases[0]), "priority": 21},
        ]})


def test_cost_lab_custom_units_are_extensible() -> None:
    assert calculate_cost(
        {"custom:gpu_seconds": 3}, [{"unit": "custom:gpu_seconds", "price_usd": "0.2"}]
    ) == Decimal("0.60000000")


def test_cost_lab_per_image_pricing_is_scoped_to_output_quality() -> None:
    prices = [
        {"unit": "output_images", "quality": "LOW", "price_usd": "0.01"},
        {"unit": "output_images", "quality": "MEDIUM", "price_usd": "0.02"},
        {"unit": "output_images", "quality": "HIGH", "price_usd": "0.04"},
    ]
    usage = {"output_images": 2, "output_quality": "MEDIUM"}
    assert calculate_cost(usage, prices) == Decimal("0.04000000")


def test_openai_image_usage_is_normalized_without_inventing_fields() -> None:
    usage = normalize_openai_usage(
        {
            "input_tokens": 120,
            "output_tokens": 800,
            "total_tokens": 920,
            "input_tokens_details": {"text_tokens": 20, "image_tokens": 100},
        }
    )
    assert usage == {
        "text_input_tokens": 20,
        "image_input_tokens": 100,
        "image_output_tokens": 800,
        "total_reported_tokens": 920,
    }


def test_byteplus_adapter_uses_json_generation_contract(monkeypatch: MonkeyPatch) -> None:
    import base64

    import requests

    class Response:
        ok = True
        headers = {"x-tt-logid": "byteplus-1"}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [{"b64_json": base64.b64encode(b"result").decode()}],
                "usage": {"total_tokens": 12, "generated_images": 1},
            }

    calls: list[dict[str, object]] = []

    def post(url: str, **kwargs: object) -> Response:
        calls.append({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(requests, "post", post)
    result = BytePlusAdapter("https://ark.ap-southeast.bytepluses.com/api/v3", "secret").generate(
        model="seedream-5-0-260128",
        prompt="try on",
        images=[b"\x89PNG\r\n\x1a\nperson", b"garment"],
        parameters={},
    )

    payload = calls[0]["json"]
    assert calls[0]["url"] == ("https://ark.ap-southeast.bytepluses.com/api/v3/images/generations")
    assert isinstance(payload, dict)
    assert payload["model"] == "seedream-5-0-260128"
    assert payload["image"] == [
        "data:image/png;base64,iVBORw0KGgpwZXJzb24=",
        "data:image/jpeg;base64,Z2FybWVudA==",
    ]
    assert payload["sequential_image_generation"] == "disabled"
    assert "output_format" not in payload
    assert result.image_bytes == b"result"
    assert result.request_id == "byteplus-1"
    assert result.usage == {"total_reported_tokens": 12, "output_images": 1}


def test_byteplus_flash_model_omits_unsupported_sequential_parameter(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        ok = True
        status_code = 200
        headers: dict[str, str] = {}

        @staticmethod
        def json() -> dict[str, object]:
            return {"data": [{"b64_json": base64.b64encode(b"result").decode()}]}

    monkeypatch.setattr(requests, "post", lambda _url, **kwargs: calls.append(kwargs) or Response())
    BytePlusAdapter("https://example.test", "secret").generate(
        model="dola-seedream-5-0-flash-260915",
        prompt="try on",
        images=[b"person", b"product"],
        parameters={"sequential_image_generation": "disabled", "size": "1248x1872"},
    )
    assert "sequential_image_generation" not in calls[0]["json"]
    assert calls[0]["json"]["size"] == "1248x1872"
    assert "2:3 aspect ratio" in calls[0]["json"]["prompt"]


def test_runware_qwen_edit_2511_sends_two_reference_images(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        ok = True
        status_code = 200

        def json(self) -> dict[str, object]:
            task_uuid = cast(list[dict[str, object]], calls[0]["json"])[0]["taskUUID"]
            return {
                "data": [
                    {
                        "taskType": "imageInference",
                        "taskUUID": task_uuid,
                        "imageUUID": "image-1",
                        "imageBase64Data": base64.b64encode(b"generated").decode(),
                        "seed": 42,
                        "cost": 0.01078,
                    }
                ]
            }

    def post(url: str, **kwargs: object) -> Response:
        calls.append({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(requests, "post", post)
    result = RunwareAdapter("https://api.runware.ai", "secret").generate(
        model="alibaba:qwen-image-edit@2511",
        prompt="Use image 1 as the person and image 2 as the garment",
        images=[b"\x89PNG\r\n\x1a\nperson", b"garment"],
        parameters={"width": 1024, "height": 1024},
    )

    payload = cast(list[dict[str, object]], calls[0]["json"])[0]
    assert calls[0]["url"] == "https://api.runware.ai/v1"
    assert payload["model"] == "alibaba:qwen-image-edit@2511"
    assert payload["inputs"] == {
        "referenceImages": [
            "data:image/png;base64,iVBORw0KGgpwZXJzb24=",
            "data:image/jpeg;base64,Z2FybWVudA==",
        ]
    }
    assert payload["outputType"] == "base64Data"
    assert payload["includeCost"] is True
    assert result.image_bytes == b"generated"
    assert result.usage == {"output_images": 1, "cost_usd": 0.01078}
    assert result.raw_metadata["cost"] == 0.01078


@pytest.mark.parametrize("count", [0, 4])
def test_runware_qwen_edit_2511_enforces_one_to_three_images(count: int) -> None:
    with pytest.raises(ValueError, match="requires 1 to 3 input images"):
        RunwareAdapter("https://api.runware.ai/v1", "secret").generate(
            model="alibaba:qwen-image-edit@2511",
            prompt="edit",
            images=[b"image"] * count,
            parameters={},
        )


def test_runware_original_qwen_edit_requires_exactly_one_image() -> None:
    with pytest.raises(ValueError, match="requires exactly 1 input image"):
        RunwareAdapter("https://api.runware.ai/v1", "secret").generate(
            model="runware:108@20",
            prompt="edit",
            images=[b"one", b"two"],
            parameters={},
        )


def test_runware_flux_klein_supports_zero_to_four_reference_images(
    monkeypatch: MonkeyPatch,
) -> None:
    adapter = RunwareAdapter("https://api.runware.ai/v1", "secret")
    captured: list[dict[str, object] | None] = []

    def generate_stub(
        _model: str,
        _prompt: str,
        _parameters: dict[str, object],
        *,
        inputs: dict[str, object] | None,
    ) -> object:
        captured.append(inputs)
        return object()

    monkeypatch.setattr(adapter, "_generate", generate_stub)
    adapter.generate(
        model="runware:400@4",
        prompt="combine references",
        images=[b"one", b"two"],
        parameters={},
    )
    adapter.generate_from_prompt(model="runware:400@4", prompt="generate")

    assert captured[0] == {
        "referenceImages": [
            "data:image/jpeg;base64,b25l",
            "data:image/jpeg;base64,dHdv",
        ]
    }
    assert captured[1] is None
    with pytest.raises(ValueError, match="requires 0 to 4 input images"):
        adapter.generate(
            model="runware:400@4",
            prompt="too many",
            images=[b"image"] * 5,
            parameters={},
        )


def test_bfl_adapter_submits_polls_and_downloads(monkeypatch: MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class Response:
        ok = True

        def __init__(self, body: dict[str, object] | None = None, content: bytes = b"") -> None:
            self._body = body or {}
            self.content = content

        def json(self) -> dict[str, object]:
            return self._body

        def raise_for_status(self) -> None:
            return None

    def post(url: str, **kwargs: object) -> Response:
        calls.append(("POST", url, cast(dict[str, object], kwargs.get("json"))))
        return Response(
            {
                "id": "generation-1",
                "polling_url": "https://api.bfl.ai/v1/get_result?id=generation-1",
            }
        )

    def get(url: str, **_: object) -> Response:
        calls.append(("GET", url, None))
        if "get_result" in url:
            return Response({"status": "Ready", "result": {"sample": "https://signed/image.jpg"}})
        return Response(content=b"generated-image")

    monkeypatch.setattr("apps.cost_lab_api.adapters.requests.post", post)
    monkeypatch.setattr("apps.cost_lab_api.adapters.requests.get", get)
    result = BFLAdapter("https://api.bfl.ai/v1", "secret", timeout=5).generate(
        model="flux-3-image-klein",
        prompt="Put the garment on the person",
        images=[b"person", b"garment"],
        parameters={},
    )

    assert calls[0][1] == "https://api.bfl.ai/v1/flux-3-image-klein"
    assert calls[0][2] == {
        "prompt": "Put the garment on the person",
        "images": ["cGVyc29u", "Z2FybWVudA=="],
    }
    assert result.image_bytes == b"generated-image"
    assert result.usage == {"output_images": 1}


def test_bfl_submission_preserves_upstream_502_without_resubmitting(
    monkeypatch: MonkeyPatch,
) -> None:
    class Response:
        ok = False
        status_code = 502
        headers = {"x-request-id": "bfl-request-502"}
        text = '{"detail":"temporary gateway failure"}'

        def json(self) -> dict[str, str]:
            return {"detail": "temporary gateway failure"}

    calls = 0

    def post(*_: object, **__: object) -> Response:
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr("apps.cost_lab_api.adapters.requests.post", post)
    with pytest.raises(BFLUpstreamError) as caught:
        BFLAdapter("https://api.bfl.ai", "secret").generate_from_prompt(
            model="flux-3-image-klein", prompt="test"
        )

    assert calls == 1
    assert caught.value.status_code == 502
    assert caught.value.response_body == {"detail": "temporary gateway failure"}
    assert caught.value.request_id == "bfl-request-502"


def test_bfl_polling_failure_preserves_job_id(monkeypatch: MonkeyPatch) -> None:
    class Response:
        headers: dict[str, str] = {}
        text = ""

        def __init__(self, status: int, body: dict[str, object]) -> None:
            self.status_code = status
            self.ok = status < 400
            self._body = body

        def json(self) -> dict[str, object]:
            return self._body

    monkeypatch.setattr(
        "apps.cost_lab_api.adapters.requests.post",
        lambda *_args, **_kwargs: Response(
            200, {"id": "job-failed", "polling_url": "https://poll/job-failed"}
        ),
    )
    monkeypatch.setattr(
        "apps.cost_lab_api.adapters.requests.get",
        lambda *_args, **_kwargs: Response(400, {"detail": "invalid job"}),
    )
    with pytest.raises(BFLUpstreamError) as caught:
        BFLAdapter("https://api.bfl.ai", "secret").generate_from_prompt(
            model="flux-3-image-klein", prompt="test"
        )

    assert caught.value.phase == "poll"
    assert caught.value.status_code == 400
    assert caught.value.job_id == "job-failed"


def test_bfl_polling_timeout_is_bounded(monkeypatch: MonkeyPatch) -> None:
    class Response:
        ok = True
        status_code = 200
        headers: dict[str, str] = {}
        text = ""

        def __init__(self, body: dict[str, object]) -> None:
            self._body = body

        def json(self) -> dict[str, object]:
            return self._body

    polls = 0
    monkeypatch.setattr(
        "apps.cost_lab_api.adapters.requests.post",
        lambda *_args, **_kwargs: Response(
            {"id": "job-pending", "polling_url": "https://poll/job-pending"}
        ),
    )

    def get(*_: object, **__: object) -> Response:
        nonlocal polls
        polls += 1
        return Response({"status": "Pending", "result": None})

    monkeypatch.setattr("apps.cost_lab_api.adapters.requests.get", get)
    monkeypatch.setattr("apps.cost_lab_api.adapters.time.sleep", lambda _: None)
    with pytest.raises(BFLUpstreamError) as caught:
        BFLAdapter(
            "https://api.bfl.ai", "secret", timeout=30, max_poll_attempts=2
        ).generate_from_prompt(model="flux-3-image-klein", prompt="test")

    assert polls == 2
    assert caught.value.phase == "timeout"
    assert caught.value.status_code == 504
    assert caught.value.job_id == "job-pending"


def test_benchmark_request_defaults_input_and_output_to_high() -> None:
    from apps.cost_lab_api.app import BenchmarkBody

    model_id = uuid4()
    body = BenchmarkBody.model_validate({"model_id": str(model_id), "category": "SAREE"})
    assert body.model_id == model_id
    assert body.input_quality == "HIGH"
    assert body.output_quality == "HIGH"
    assert body.image_count == 10
    assert body.category == "SAREE"


def test_benchmark_request_accepts_separate_image_qualities() -> None:
    from apps.cost_lab_api.app import BenchmarkBody

    body = BenchmarkBody.model_validate(
        {
            "model_id": str(uuid4()),
            "category": "JEWELLERY",
            "input_quality": "LOW",
            "output_quality": "MEDIUM",
        }
    )
    assert body.input_quality == "LOW"
    assert body.output_quality == "MEDIUM"


def test_benchmark_request_accepts_selected_image_count() -> None:
    from apps.cost_lab_api.app import BenchmarkBody

    body = BenchmarkBody.model_validate(
        {"model_id": str(uuid4()), "category": "DRESS", "image_count": 25}
    )
    assert body.image_count == 25


def test_benchmark_request_accepts_optional_person_selection() -> None:
    from apps.cost_lab_api.app import BenchmarkBody

    person_id = uuid4()
    body = BenchmarkBody.model_validate(
        {
            "model_id": str(uuid4()),
            "category": "SAREE",
            "person_asset_id": str(person_id),
        }
    )
    assert body.person_asset_id == person_id


def test_benchmark_request_accepts_result_as_person() -> None:
    from apps.cost_lab_api.app import BenchmarkBody

    tryon_id = uuid4()
    body = BenchmarkBody.model_validate(
        {
            "model_id": str(uuid4()),
            "category": "DRESS",
            "person_result_tryon_id": str(tryon_id),
        }
    )
    assert body.person_result_tryon_id == tryon_id


@pytest.mark.parametrize("image_count", [0, 101])
def test_benchmark_request_rejects_unsafe_image_count(image_count: int) -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import BenchmarkBody

    with pytest.raises(ValidationError):
        BenchmarkBody.model_validate(
            {"model_id": str(uuid4()), "category": "SAREE", "image_count": image_count}
        )


def test_benchmark_request_requires_supported_product_category() -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import BenchmarkBody

    with pytest.raises(ValidationError):
        BenchmarkBody.model_validate(
            {"model_id": str(uuid4()), "category": "PERSON", "image_count": 1}
        )


def test_final_check_requires_model_and_person() -> None:
    from apps.cost_lab_api.app import FinalCheckBody

    model_id, person_id = uuid4(), uuid4()
    body = FinalCheckBody.model_validate(
        {"model_id": str(model_id), "person_asset_id": str(person_id)}
    )
    assert body.model_id == model_id
    assert body.person_asset_id == person_id


def test_benchmark_and_final_check_accept_input_complexity() -> None:
    from apps.cost_lab_api.app import BenchmarkBody, FinalCheckBody

    benchmark = BenchmarkBody.model_validate({
        "model_id": str(uuid4()), "category": "JEWELLERY",
        "input_complexity": "COMPLEX",
    })
    assert benchmark.input_complexity == "COMPLEX"
    final = FinalCheckBody.model_validate({
        "model_id": str(uuid4()), "person_asset_id": str(uuid4()),
        "jewellery_complexity": "COMPLEX", "saree_complexity": "SIMPLE",
        "dress_complexity": "MEDIUM",
    })
    assert final.jewellery_complexity == "COMPLEX"
    assert final.saree_complexity == "SIMPLE"


def test_final_review_scores_are_bounded() -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import FinalReviewsBody

    with pytest.raises(ValidationError):
        FinalReviewsBody.model_validate(
            {"reviews": [{"tryon_id": str(uuid4()), "score": 11, "comment": "Good"}]}
        )


def test_final_review_comment_is_optional() -> None:
    from apps.cost_lab_api.app import FinalReviewsBody

    body = FinalReviewsBody.model_validate(
        {"reviews": [{"tryon_id": str(uuid4()), "score": 9}]}
    )
    assert body.reviews[0].comment == ""


def test_final_check_score_summary_is_quality_aware() -> None:
    from apps.cost_lab_api.app import final_check_score_summary

    rows = [
        {"category": "JEWELLERY", "quality": "LOW", "score": 6},
        {"category": "JEWELLERY", "quality": "LOW", "score": 8},
        {"category": "SAREE", "quality": "HIGH", "score": 10},
    ]
    assert final_check_score_summary(rows) == {
        "review_count": 3,
        "average_score": 8.0,
        "minimum_score": 6,
        "maximum_score": 10,
        "by_category_quality": {
            "JEWELLERY:LOW": {"count": 2, "average": 7.0},
            "SAREE:HIGH": {"count": 1, "average": 10.0},
        },
    }


def test_production_promotion_requires_unique_quality_levels() -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import PromoteFinalCheckBody

    body = PromoteFinalCheckBody.model_validate({"quality_levels": ["LOW", "HIGH"]})
    assert body.quality_levels == ["LOW", "HIGH"]
    with pytest.raises(ValidationError):
        PromoteFinalCheckBody.model_validate({"quality_levels": ["HIGH", "HIGH"]})


def test_dataset_generation_accepts_category_count_prompt_quality_and_direction() -> None:
    from apps.cost_lab_api.app import DatasetGenerationBody

    model_id = uuid4()
    body = DatasetGenerationBody.model_validate(
        {
            "model_id": str(model_id),
            "generation_quality": "HIGH",
            "category": "JEWELLERY",
            "count": 24,
            "prompt": "Create antique temple jewellery on white.",
            "direction": "Use rich silk fabrics and warm studio lighting.",
        }
    )

    assert body.model_id == model_id
    assert body.generation_quality == "HIGH"
    assert body.category == "JEWELLERY"
    assert body.count == 24
    assert body.prompt == "Create antique temple jewellery on white."
    assert body.direction == "Use rich silk fabrics and warm studio lighting."


def test_dataset_generation_instruction_requires_one_product_per_image() -> None:
    from apps.cost_lab_api.app import _single_item_dataset_instruction

    instruction = _single_item_dataset_instruction("DRESS", 2, 5)

    assert "exactly ONE standalone wearable product" in instruction
    assert "distribution across the whole batch" in instruction
    assert "dataset image 3 of 5" in instruction
    assert "collage" in instruction


def test_dataset_generation_without_quality_defaults_to_high() -> None:
    from apps.cost_lab_api.app import DatasetGenerationBody

    body = DatasetGenerationBody.model_validate({"model_id": str(uuid4()), "category": "PERSON"})
    assert body.generation_quality == "HIGH"
    assert body.category == "PERSON"


def test_dataset_generation_requires_category() -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import DatasetGenerationBody

    with pytest.raises(ValidationError):
        DatasetGenerationBody.model_validate({"model_id": str(uuid4())})


@pytest.mark.parametrize("count", [0, 101])
def test_dataset_generation_rejects_unsafe_count(count: int) -> None:
    from pydantic import ValidationError

    from apps.cost_lab_api.app import DatasetGenerationBody

    with pytest.raises(ValidationError):
        DatasetGenerationBody.model_validate(
            {"model_id": str(uuid4()), "category": "SAREE", "count": count}
        )


def test_model_and_pricing_are_one_request_unit() -> None:
    from apps.cost_lab_api.app import ModelWithPricingBody

    body = ModelWithPricingBody.model_validate(
        {
            "provider_id": str(uuid4()),
            "name": "Image model",
            "api_identifier": "image-model-v1",
            "quality_levels": ["LOW", "MEDIUM", "HIGH"],
            "image_input_price_usd_per_million": "10",
            "image_output_price_usd_per_million": "40",
        }
    )
    assert body.image_input_price_usd_per_million == Decimal("10")
    assert body.image_output_price_usd_per_million == Decimal("40")


def test_model_pricing_accepts_quality_based_output_image_prices() -> None:
    from apps.cost_lab_api.app import ModelWithPricingBody, _model_pricing_components

    body = ModelWithPricingBody.model_validate(
        {
            "provider_id": str(uuid4()),
            "name": "BFL Image model",
            "api_identifier": "bfl-image-v1",
            "output_image_price_usd_low": "0.01",
            "output_image_price_usd_medium": "0.02",
            "output_image_price_usd_high": "0.04",
        }
    )

    assert _model_pricing_components(body) == [
        {"unit": "output_images", "quality": "LOW", "price_usd": "0.01"},
        {"unit": "output_images", "quality": "MEDIUM", "price_usd": "0.02"},
        {"unit": "output_images", "quality": "HIGH", "price_usd": "0.04"},
    ]


def test_promoted_model_pricing_update_contains_prices_only() -> None:
    from apps.cost_lab_api.app import ProductionPricingBody, _model_pricing_components

    body = ProductionPricingBody.model_validate(
        {
            "image_input_price_usd_per_million": "8.50",
            "output_image_price_usd_high": "0.04",
        }
    )
    assert _model_pricing_components(body) == [
        {"unit": "image_input_tokens", "price_usd": "8.50"},
        {"unit": "output_images", "quality": "HIGH", "price_usd": "0.04"},
    ]
    with pytest.raises(ValueError):
        ProductionPricingBody.model_validate({"name": "cannot rename production model"})


def test_provider_accepts_pricing_reference_url_or_text() -> None:
    from apps.cost_lab_api.app import ProviderBody

    body = ProviderBody.model_validate(
        {
            "name": "BytePlus",
            "provider_type": "BYTEPLUS",
            "secret_reference": "env:WEARO_BYTEPLUS_API_KEY",
            "pricing_reference_url": "https://docs.byteplus.com/pricing",
            "pricing_reference_text": "Image generation prices effective November 2026.",
        }
    )
    assert str(body.pricing_reference_url) == "https://docs.byteplus.com/pricing"
    assert body.pricing_reference_text == "Image generation prices effective November 2026."


def test_llm_knowledge_blocks_render_only_safe_semantic_html() -> None:
    from apps.cost_lab_api.app import _structured_knowledge_html

    rendered = _structured_knowledge_html(
        {
            "blocks": [
                {"type": "heading", "level": 2, "text": "Pricing <guide>", "items": []},
                {"type": "paragraph", "level": 2, "text": "Keep every fact.", "items": []},
                {
                    "type": "bullets",
                    "level": 2,
                    "text": "",
                    "items": ["Input tokens", "<script>alert(1)</script>"],
                },
            ]
        }
    )

    assert "<h2>Pricing &lt;guide&gt;</h2>" in rendered
    assert "<ul><li>Input tokens</li>" in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_cost_lab_auth_alias_is_a_dependency_not_a_query_parameter(tmp_path: Path) -> None:
    from cryptography.fernet import Fernet
    from fastapi.routing import APIRoute
    from sqlalchemy import Engine, create_mock_engine

    from apps.api.wearo_api.admin_auth import hash_password
    from apps.cost_lab_api.app import create_app
    from apps.cost_lab_api.config import Settings

    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        admin_username="admin",
        password_hash=hash_password("test-value").decode(),
        session_secret="x" * 32,
        encryption_key=Fernet.generate_key().decode(),
        session_ttl_minutes=60,
        secure_cookie=False,
        storage_root=tmp_path,
        fx_url="https://example.invalid",
    )
    engine = cast(Engine, create_mock_engine("postgresql+psycopg://", lambda *args: None))
    app = create_app(settings, engine)
    route = cast(
        APIRoute,
        next(
            item for item in app.routes if getattr(item, "path", "") == "/api/cost-lab/auth/session"
        ),
    )
    assert not route.dependant.query_params
    assert len(route.dependant.dependencies) == 1
