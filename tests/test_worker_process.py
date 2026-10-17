from pathlib import Path
from typing import cast

import pytest

from apps.api.wearo_api.external_runtime import OpenAIAnalysisClient
from apps.api.wearo_api.render_provider import OpenAIImageEditAdapter
from apps.api.wearo_api.render_quality import RenderQualityGate
from apps.api.wearo_api.worker_process import build_worker


def configure_common(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEARO_DATABASE_URL", "postgresql://wearo:test@127.0.0.1:55432/wearo")
    monkeypatch.setenv("WEARO_ANALYSIS_ENDPOINT", "https://analysis.example.test/v1/evaluate")
    monkeypatch.setenv("WEARO_ANALYSIS_TOKEN", "analysis-secret")
    monkeypatch.setenv("WEARO_PRIVATE_STORAGE_ROOT", str(tmp_path))


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
