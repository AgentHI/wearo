from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

PrincipalType = Literal["CONSUMER", "BUSINESS"]
TenantRole = Literal["OWNER", "ASSOCIATE"]


class AuthorizationError(PermissionError):
    """Generic authorization denial that does not disclose resource existence."""


@dataclass(frozen=True)
class PrincipalContext:
    principal_id: UUID
    account_id: UUID
    principal_type: PrincipalType
    status: str


@dataclass(frozen=True)
class TenantAccess:
    tenant_id: UUID
    account_id: UUID
    principal_id: UUID
    role: TenantRole
    revoked_at: datetime | None
    tenant_status: str


@dataclass(frozen=True)
class Entitlement:
    account_id: UUID
    tenant_id: UUID | None
    offering: str
    enabled: bool
    effective_from: datetime
    effective_until: datetime | None


class AuthorizationStore(Protocol):
    def get_principal(self, principal_id: UUID) -> PrincipalContext | None: ...

    def get_tenant_access(self, principal_id: UUID, tenant_id: UUID) -> TenantAccess | None: ...

    def get_entitlements(self, account_id: UUID, offering: str) -> tuple[Entitlement, ...]: ...


class AuthorizationService:
    def __init__(self, store: AuthorizationStore) -> None:
        self.store = store

    def require_principal(self, principal_id: UUID) -> PrincipalContext:
        principal = self.store.get_principal(principal_id)
        if principal is None or principal.status != "ACTIVE":
            raise AuthorizationError("resource unavailable")
        return principal

    def require_account(self, principal_id: UUID, resource_account_id: UUID) -> PrincipalContext:
        principal = self.require_principal(principal_id)
        if principal.account_id != resource_account_id:
            raise AuthorizationError("resource unavailable")
        return principal

    def require_tenant(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        roles: frozenset[TenantRole] = frozenset({"OWNER", "ASSOCIATE"}),
    ) -> TenantAccess:
        principal = self.require_principal(principal_id)
        access = self.store.get_tenant_access(principal.principal_id, tenant_id)
        if (
            access is None
            or access.account_id != principal.account_id
            or access.principal_id != principal.principal_id
            or access.revoked_at is not None
            or access.tenant_status != "ACTIVE"
            or access.role not in roles
        ):
            raise AuthorizationError("resource unavailable")
        return access

    def require_entitlement(
        self,
        principal_id: UUID,
        offering: str,
        *,
        tenant_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Entitlement:
        current = now or datetime.now(UTC)
        principal = self.require_principal(principal_id)
        if tenant_id is not None:
            self.require_tenant(principal_id, tenant_id)
        candidates = self.store.get_entitlements(principal.account_id, offering)
        active = tuple(
            item
            for item in candidates
            if item.enabled
            and item.account_id == principal.account_id
            and item.tenant_id == tenant_id
            and item.effective_from <= current
            and (item.effective_until is None or item.effective_until > current)
        )
        if len(active) != 1:
            raise AuthorizationError("resource unavailable")
        return active[0]
