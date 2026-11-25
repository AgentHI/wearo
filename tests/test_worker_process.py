from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from apps.api.wearo_api.external_runtime import OpenAIAnalysisClient
from apps.api.wearo_api.render_provider import (
    PERSON_PRESERVATION_NEGATIVE_PROMPT,
    PERSON_PRESERVATION_PROMPT,
    OpenAIImageEditAdapter,
    RenderRequest,
)
from apps.api.wearo_api.render_quality import RenderQualityGate
from apps.api.wearo_api.worker_process import (
    _CostLabProductionAdapter,
    build_worker,
    worker_concurrency,
)


def configure_common(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEARO_DATABASE_URL", "postgresql://wearo:test@127.0.0.1:55432/wearo")
    monkeypatch.setenv("WEARO_ANALYSIS_ENDPOINT", "https://analysis.example.test/v1/evaluate")
    monkeypatch.setenv("WEARO_ANALYSIS_TOKEN", "analysis-secret")
    monkeypatch.setenv("WEARO_PRIVATE_STORAGE_ROOT", str(tmp_path))


class CaptureGenerationAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            image_bytes=b"\x89PNG\r\n\x1a\nresult",
            usage={},
            request_id="runware-request",
        )


def _production_request(product_kind: str) -> RenderRequest:
    return RenderRequest(
        person_image=b"person",
        item_image=b"item",
        person_mime="image/jpeg",
        item_mime="image/jpeg",
        capability="APPAREL",
        product_kind=product_kind,
    )


def _runware_production_adapter() -> tuple[_CostLabProductionAdapter, CaptureGenerationAdapter]:
    provider = _CostLabProductionAdapter(
        provider="RUNWARE",
        model="runware:400@4",
        region="global",
        base_url="https://api.runware.ai/v1",
        api_key="runware-secret",
    )
    capture = CaptureGenerationAdapter()
    provider.adapter = cast(Any, capture)
    return provider, capture


def test_production_apparel_prompt_locks_face_and_body_structure() -> None:
    provider, capture = _runware_production_adapter()

    provider.render(_production_request("APPAREL"))

    call = capture.calls[0]
    assert str(call["prompt"]).startswith(PERSON_PRESERVATION_PROMPT)
    assert "Never make the person wider, narrower" in str(call["prompt"])
    assert PERSON_PRESERVATION_NEGATIVE_PROMPT in call["parameters"]["negativePrompt"]


def test_production_jewellery_keeps_existing_prompt_and_adds_person_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.cost_lab_api.app import (
        _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT,
        _RUNWARE_NECKLACE_ONLY_PROMPT,
    )

    monkeypatch.setattr(
        "apps.cost_lab_api.jewellery_references.plan_runware_jewellery_references",
        lambda _person, _item: SimpleNamespace(
            images=(b"person", b"necklace"), strategy="person_necklace"
        ),
    )
    provider, capture = _runware_production_adapter()

    provider.render(_production_request("JEWELLERY"))

    call = capture.calls[0]
    assert str(call["prompt"]).startswith(PERSON_PRESERVATION_PROMPT)
    assert _RUNWARE_NECKLACE_ONLY_PROMPT in str(call["prompt"])
    assert _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT in call["parameters"]["negativePrompt"]
    assert PERSON_PRESERVATION_NEGATIVE_PROMPT in call["parameters"]["negativePrompt"]


def test_worker_builds_openai_provider_without_google_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_common(monkeypatch, tmp_path)
    monkeypatch.setenv("WEARO_RENDER_PROVIDER", "OPENAI")
    monkeypatch.setenv("WEARO_OPENAI_ENABLED", "true")
    monkeypatch.setenv("WEARO_OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("WEARO_OPENAI_MODEL", "gpt-image-2.5-flare")
    monkeypatch.setenv("WEARO_OPENAI_ANALYSIS_MODEL", "gpt-6-luna")
    monkeypatch.delenv("WEARO_ANALYSIS_ENDPOINT", raising=False)
    monkeypatch.delenv("WEARO_ANALYSIS_TOKEN", raising=False)
    monkeypatch.delenv("WEARO_VERTEX_PROJECT_ID", raising=False)

    worker = build_worker()

    assert isinstance(worker.provider, OpenAIImageEditAdapter)
    assert worker.provider.model == "gpt-image-2.5-flare"
    assert worker.provider.streaming is False
    assert worker.provider.connect_timeout_seconds == 15
    assert worker.provider.read_timeout_seconds == 180
    quality = cast(RenderQualityGate, worker.quality)
    assert isinstance(quality.analyzer, OpenAIAnalysisClient)
    assert quality.analyzer.model == "gpt-6-luna"


def test_worker_openai_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_common(monkeypatch, tmp_path)
    monkeypatch.setenv("WEARO_RENDER_PROVIDER", "OPENAI")
    monkeypatch.setenv("WEARO_OPENAI_ENABLED", "false")
    with pytest.raises(SystemExit, match="WEARO_OPENAI_ENABLED=true is required"):
        build_worker()

    monkeypatch.setenv("WEARO_OPENAI_ENABLED", "true")
    monkeypatch.setenv("WEARO_OPENAI_API_KEY", "")
    with pytest.raises(SystemExit, match="WEARO_OPENAI_API_KEY is required"):
        build_worker()


def test_worker_concurrency_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEARO_WORKER_CONCURRENCY", "6")
    assert worker_concurrency() == 6
    assert worker_concurrency(2) == 2
    with pytest.raises(SystemExit, match="between 1 and 32"):
        worker_concurrency(0)
    with pytest.raises(SystemExit, match="between 1 and 32"):
        worker_concurrency(33)
    with pytest.raises(SystemExit, match="integer"):
        worker_concurrency("many")


def test_worker_applies_openai_image_transport_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_common(monkeypatch, tmp_path)
    monkeypatch.setenv("WEARO_RENDER_PROVIDER", "OPENAI")
    monkeypatch.setenv("WEARO_OPENAI_ENABLED", "true")
    monkeypatch.setenv("WEARO_OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("OPENAI_IMAGE_STREAMING", "true")
    monkeypatch.setenv("OPENAI_IMAGE_CONNECT_TIMEOUT", "12")
    monkeypatch.setenv("OPENAI_IMAGE_READ_TIMEOUT", "240")
    worker = build_worker()
    provider = cast(OpenAIImageEditAdapter, worker.provider)
    assert provider.streaming is True
    assert provider.connect_timeout_seconds == 12
    assert provider.read_timeout_seconds == 240


def test_worker_uses_an_explicit_shared_database_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_common(monkeypatch, tmp_path)
    monkeypatch.setenv("WEARO_RENDER_PROVIDER", "OPENAI")
    monkeypatch.setenv("WEARO_OPENAI_ENABLED", "true")
    monkeypatch.setenv("WEARO_OPENAI_API_KEY", "openai-secret")
    shared_engine = cast(Any, object())

    worker = build_worker(engine=shared_engine)

    assert worker.runtime.engine is shared_engine  # type: ignore[attr-defined]
    assert worker.media.engine is shared_engine  # type: ignore[attr-defined]
