import os
from pathlib import Path

import pytest

from apps.api.wearo_api.environment import load_wearo_environment


def test_local_dotenv_can_explicitly_override_stale_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEARO_OPENAI_ENABLED", "false")
    (tmp_path / ".env").write_text(
        "WEARO_LOCAL_DOTENV_OVERRIDE=true\nWEARO_OPENAI_ENABLED=true\n",
        encoding="utf-8",
    )

    load_wearo_environment()

    assert os.environ["WEARO_OPENAI_ENABLED"] == "true"


def test_dotenv_preserves_export_without_explicit_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEARO_OPENAI_ENABLED", "false")
    (tmp_path / ".env").write_text("WEARO_OPENAI_ENABLED=true\n", encoding="utf-8")

    load_wearo_environment()

    assert os.environ["WEARO_OPENAI_ENABLED"] == "false"
