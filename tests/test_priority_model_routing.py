from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine

from apps.api.wearo_api.admin_ai_costs import PostgresTryOnRouteRegistry
from apps.api.wearo_api.postgres_beta import PostgresQuoteStore
from apps.api.wearo_api.render_preflight import BetaRenderQuote, ModelRoute


class _Result:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        row: dict[str, Any] | None = None,
    ) -> None:
        self.rows = rows or []
        self.row = row

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row


class _Connection:
    def __init__(self, results: list[_Result]) -> None:
        self.results = iter(results)
        self.statements: list[str] = []
        self.parameters: list[dict[str, Any]] = []

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object, parameters: dict[str, Any] | None = None) -> _Result:
        self.statements.append(str(statement))
        self.parameters.append(parameters or {})
        return next(self.results)


class _Engine:
    def __init__(self, results: list[_Result]) -> None:
        self.connection = _Connection(results)

    def connect(self) -> _Connection:
        return self.connection

    def begin(self) -> _Connection:
        return self.connection


def test_registry_returns_promoted_models_in_database_priority_order() -> None:
    first_release, second_release = uuid4(), uuid4()
    engine = _Engine(
        [
            _Result(
                rows=[
                    {
                        "provider": "BYTEPLUS",
                        "model": "primary-model",
                        "region": "ap-southeast-1",
                        "priority": 1,
                        "release_id": first_release,
                    },
                    {
                        "provider": "BFL",
                        "model": "fallback-model",
                        "region": "global",
                        "priority": 2,
                        "release_id": second_release,
                    },
                ]
            )
        ]
    )

    routes = PostgresTryOnRouteRegistry(cast(Engine, engine)).routes_for(
        "APPAREL", datetime.now(UTC)
    )

    assert [(route.priority, route.model) for route in routes] == [
        (1, "primary-model"),
        (2, "fallback-model"),
    ]
    assert [route.release_id for route in routes] == [first_release, second_release]
    assert "ORDER BY r.priority" in engine.connection.statements[0]


def test_quote_store_snapshots_every_route_candidate() -> None:
    primary = ModelRoute("BYTEPLUS", "primary-model", "ap-southeast-1", "APPAREL", True, 1)
    fallback = ModelRoute("BFL", "fallback-model", "global", "APPAREL", True, 2)
    quote = BetaRenderQuote(
        quote_id=uuid4(),
        account_id=uuid4(),
        principal_id=uuid4(),
        profile_id=uuid4(),
        person_asset_id=uuid4(),
        consent_id=uuid4(),
        item_asset_id=uuid4(),
        route=primary,
        remaining_before=3,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        limitation="AI preview",
        fallback_routes=(fallback,),
    )
    engine = _Engine([_Result()])

    PostgresQuoteStore(cast(Engine, engine)).create(quote)

    candidates = json.loads(engine.connection.parameters[0]["route_candidates"])
    assert [(item["priority"], item["model"]) for item in candidates] == [
        (1, "primary-model"),
        (2, "fallback-model"),
    ]
