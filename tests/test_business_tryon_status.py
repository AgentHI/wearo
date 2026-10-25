# mypy: ignore-errors

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.api.wearo_api import business_tryon_status as status_module
from apps.api.wearo_api.business_tryon_status import (
    BusinessTryOnStatusError,
    PostgresBusinessTryOnStatus,
)


class Result:
    def __init__(self, scalar=None) -> None:
        self.scalar = scalar

    def scalar_one(self):
        return self.scalar


class Connection:
    def __init__(self, status: str) -> None:
        self.status = status
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, values=None):
        sql = str(statement)
        values = values or {}
        self.calls.append((sql, values))
        if "SELECT try_on_status" in sql:
            return Result(self.status)
        if "UPDATE business_tenants SET try_on_status" in sql:
            self.status = values["status"]
        return Result()


class Context:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_):
        return False


class Engine:
    def __init__(self, status: str) -> None:
        self.connection = Connection(status)

    def connect(self):
        return Context(self.connection)

    def begin(self):
        return Context(self.connection)


@pytest.fixture(autouse=True)
def owner_scope(monkeypatch):
    account_id = uuid4()
    monkeypatch.setattr(
        status_module,
        "require_tenant_scope",
        lambda connection, principal_id, tenant_id, roles: SimpleNamespace(account_id=account_id),
    )


@pytest.mark.parametrize(
    ("initial", "target"),
    (("ACTIVE", "PAUSED"), ("PAUSED", "ACTIVE"), ("ACTIVE", "CANCELLED"), ("PAUSED", "CANCELLED")),
)
def test_allowed_business_try_on_status_transitions(initial: str, target: str) -> None:
    engine = Engine(initial)
    result = PostgresBusinessTryOnStatus(engine).transition(
        uuid4(), uuid4(), target, now=datetime(2026, 10, 25, tzinfo=UTC)
    )

    assert result == {"status": target}
    assert engine.connection.status == target
    sql = "\n".join(call[0] for call in engine.connection.calls)
    assert "DELETE" not in sql
    if target == "CANCELLED":
        assert "UPDATE plan_assignments" in sql
    else:
        assert "UPDATE plan_assignments" not in sql


@pytest.mark.parametrize("target", ("ACTIVE", "PAUSED"))
def test_cancelled_business_subscription_is_terminal(target: str) -> None:
    engine = Engine("CANCELLED")

    with pytest.raises(BusinessTryOnStatusError) as error:
        PostgresBusinessTryOnStatus(engine).transition(uuid4(), uuid4(), target)

    assert error.value.code == "TRY_ON_STATUS_CONFLICT"
    assert engine.connection.status == "CANCELLED"


def test_repeating_the_current_status_is_idempotent() -> None:
    engine = Engine("PAUSED")

    assert PostgresBusinessTryOnStatus(engine).transition(uuid4(), uuid4(), "PAUSED") == {
        "status": "PAUSED"
    }
    assert not any(
        "UPDATE business_tenants SET try_on_status" in sql for sql, _ in engine.connection.calls
    )


def test_try_on_creation_paths_enforce_business_status() -> None:
    sponsored = open("apps/api/wearo_api/sponsored_tryons.py").read()
    runtime = open("apps/api/wearo_api/render_runtime.py").read()

    assert sponsored.count("authorize_business_try_on(") == 2
    assert "authorize_business_try_on(cast(BusinessTryOnStatus, sponsored_status))" in runtime
