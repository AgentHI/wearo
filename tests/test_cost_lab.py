from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import uuid4

from pytest import MonkeyPatch

from apps.cost_lab_api.adapters import BytePlusAdapter, normalize_openai_usage
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


def test_cost_lab_custom_units_are_extensible() -> None:
    assert calculate_cost(
        {"custom:gpu_seconds": 3}, [{"unit": "custom:gpu_seconds", "price_usd": "0.2"}]
    ) == Decimal("0.60000000")


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
    result = BytePlusAdapter(
        "https://ark.ap-southeast.bytepluses.com/api/v3", "secret"
    ).generate(
        model="seedream-5-0-260128",
        prompt="try on",
        images=[b"\x89PNG\r\n\x1a\nperson", b"garment"],
        parameters={},
    )

    payload = calls[0]["json"]
    assert calls[0]["url"] == (
        "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"
    )
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


def test_benchmark_request_only_requires_a_model() -> None:
    from apps.cost_lab_api.app import BenchmarkBody

    model_id = uuid4()
    assert BenchmarkBody.model_validate({"model_id": str(model_id)}).model_id == model_id


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
