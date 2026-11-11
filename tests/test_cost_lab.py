import base64
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
import requests
from pytest import MonkeyPatch

from apps.cost_lab_api.adapters import (
    BFLAdapter,
    BFLUpstreamError,
    BytePlusAdapter,
    normalize_openai_usage,
)
from apps.cost_lab_api.app import reproducible_combinations
from apps.cost_lab_api.pricing import calculate_cost, normalized_total_tokens


def test_cost_lab_pricing_supports_disjoint_units() -> None:
    usage = {"text_input_tokens": 1_000_000, "image_output_tokens": 500_000, "requests": 2}
    prices = [
        {"unit": "text_input_tokens", "price_usd": "2"},
        {"unit": "image_output_tokens", "price_usd": "8"},
        {"unit": "requests", "price_usd": "0.25"},
    ]
    assert calculate_cost(usage, prices) == Decimal("6.50000000")


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
        parameters={"sequential_image_generation": "disabled", "size": "1.5K"},
    )
    assert "sequential_image_generation" not in calls[0]["json"]
    assert calls[0]["json"]["size"] == "1.5K"
    assert "2:3 aspect ratio" in calls[0]["json"]["prompt"]


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
