from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Connection as SqlAlchemyConnection

from apps.api.wearo_api.tenant_scope import TenantScopeError, require_tenant_scope


class Result:
    def __init__(self, row: object | None) -> None:
        self.row = row

    def one_or_none(self) -> object | None:
        return self.row


class Row:
    def __init__(self, account_id: object, role: str) -> None:
        self._mapping = {"account_id": account_id, "role": role}


class Connection:
    def __init__(self, row: object | None) -> None:
        self.row = row

    def execute(self, statement: object, parameters: object) -> Result:
        return Result(self.row)


def test_scope_returns_account_only_for_allowed_active_membership() -> None:
    account_id, principal_id, tenant_id = uuid4(), uuid4(), uuid4()
    scope = require_tenant_scope(
        cast(SqlAlchemyConnection, Connection(Row(account_id, "ASSOCIATE"))),
        principal_id,
        tenant_id,
    )
    assert (scope.account_id, scope.tenant_id, scope.principal_id) == (
        account_id,
        tenant_id,
        principal_id,
    )


def test_foreign_or_inactive_tenant_has_same_opaque_denial() -> None:
    with pytest.raises(TenantScopeError, match="resource unavailable"):
        require_tenant_scope(cast(SqlAlchemyConnection, Connection(None)), uuid4(), uuid4())


def test_associate_cannot_enter_owner_scope() -> None:
    with pytest.raises(TenantScopeError, match="resource unavailable"):
        require_tenant_scope(
            cast(SqlAlchemyConnection, Connection(Row(uuid4(), "ASSOCIATE"))),
            uuid4(),
            uuid4(),
            roles=frozenset({"OWNER"}),
        )
