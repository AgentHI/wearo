from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, text

TenantRole = Literal["OWNER", "ASSOCIATE"]


class TenantScopeError(PermissionError):
    """Opaque denial for missing, foreign, inactive, or revoked tenant access."""


@dataclass(frozen=True)
class TenantScope:
    tenant_id: UUID
    account_id: UUID
    principal_id: UUID
    role: TenantRole


def require_tenant_scope(
    connection: Connection,
    principal_id: UUID,
    tenant_id: UUID,
    *,
    roles: frozenset[TenantRole] = frozenset({"OWNER", "ASSOCIATE"}),
) -> TenantScope:
    row = connection.execute(
        text(
            """
            SELECT m.account_id, m.role
            FROM tenant_memberships m
            JOIN business_tenants t
              ON t.tenant_id = m.tenant_id AND t.account_id = m.account_id
            JOIN principals p
              ON p.principal_id = m.principal_id AND p.account_id = m.account_id
            JOIN accounts a ON a.account_id = m.account_id
            WHERE m.principal_id = :principal AND m.tenant_id = :tenant
              AND m.revoked_at IS NULL AND t.status = 'ACTIVE'
              AND p.status = 'ACTIVE' AND a.status = 'ACTIVE'
            """
        ),
        {"principal": principal_id, "tenant": tenant_id},
    ).one_or_none()
    if row is None or row._mapping["role"] not in roles:
        raise TenantScopeError("resource unavailable")
    return TenantScope(tenant_id, row._mapping["account_id"], principal_id, row._mapping["role"])
