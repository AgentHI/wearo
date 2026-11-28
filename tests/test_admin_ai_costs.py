from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine

from apps.api.wearo_api.admin_ai_costs import PostgresAdminAiCosts


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class _Connection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statement = ""

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object) -> _Result:
        self.statement = str(statement)
        return _Result(self.rows)


class _Engine:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.connection = _Connection(rows)

    def connect(self) -> _Connection:
        return self.connection


def test_admin_ai_cost_dashboard_uses_active_cost_lab_promotions() -> None:
    provider_id = uuid4()
    base = {
        "provider_id": provider_id,
        "provider_name": "Provider One",
        "provider_type": "OPENAI_COMPATIBLE",
        "api_base_url": "https://models.example.test",
        "provider_enabled": True,
    }
    engine = _Engine(
        [
            base | {"model_name": "Model A", "priority": 1},
            base | {"model_name": "Model B", "priority": 2},
        ]
    )

    dashboard = PostgresAdminAiCosts(cast(Engine, engine)).dashboard()
    models = cast(list[dict[str, Any]], dashboard["models"])
    providers = cast(list[dict[str, Any]], dashboard["providers"])

    assert [model["model_name"] for model in models] == ["Model A", "Model B"]
    assert providers == [
        {
            **base,
            "promoted_model_count": 2,
        }
    ]
    assert "cost_lab.production_model_releases" in engine.connection.statement
    assert "r.retired_at IS NULL" in engine.connection.statement
    assert "ORDER BY r.priority" in engine.connection.statement
