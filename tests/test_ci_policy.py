from pathlib import Path

import pytest

from scripts.validate_ci import CIPolicyError, validate_workflow

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_has_all_blocking_gates() -> None:
    validate_workflow(WORKFLOW.read_text(encoding="utf-8"))


def test_missing_gate_is_rejected() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    deliberately_broken = workflow.replace("      - run: uv run mypy\n", "")

    with pytest.raises(CIPolicyError, match="uv run mypy"):
        validate_workflow(deliberately_broken)


def test_continue_on_error_is_rejected() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    with pytest.raises(CIPolicyError, match="continue-on-error"):
        validate_workflow(f"{workflow}\ncontinue-on-error: true\n")
