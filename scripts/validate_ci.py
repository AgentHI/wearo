#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_JOBS = (
    "contracts:",
    "python-quality:",
    "migrations:",
    "dependency-security:",
)
REQUIRED_COMMANDS = (
    "pnpm install --frozen-lockfile",
    "node-version: 22",
    "pnpm validate:backlog",
    "pnpm lint:openapi",
    "pnpm check:contracts",
    "uv sync --frozen --extra dev",
    "uv run ruff format --check .",
    "uv run ruff check .",
    "uv run mypy",
    "uv run pytest",
    "uv run python scripts/validate_ci.py",
    "sh scripts/rehearse_migrations.sh",
    "uv run pytest -m integration",
    "uv run pip-audit",
    "pnpm audit --audit-level high",
)


class CIPolicyError(ValueError):
    """Raised when a required CI gate is absent or non-blocking."""


def validate_workflow(text: str) -> None:
    missing = [item for item in (*REQUIRED_JOBS, *REQUIRED_COMMANDS) if item not in text]
    if missing:
        raise CIPolicyError(f"Missing required CI entries: {', '.join(missing)}")
    if "continue-on-error: true" in text:
        raise CIPolicyError("Required CI checks must not use continue-on-error")
    if "permissions:\n  contents: read" not in text:
        raise CIPolicyError("CI must use read-only repository permissions")


def main() -> None:
    validate_workflow(WORKFLOW.read_text(encoding="utf-8"))
    print("CI policy validation: PASS")


if __name__ == "__main__":
    main()
