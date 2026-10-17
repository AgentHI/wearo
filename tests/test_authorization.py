from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.authorization import (
    AuthorizationError,
    AuthorizationService,
    Entitlement,
    PrincipalContext,
    TenantAccess,
)

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class MemoryStore:
    def __init__(self) -> None:
        self.principals: dict[UUID, PrincipalContext] = {}
        self.access: dict[tuple[UUID, UUID], TenantAccess] = {}
        self.entitlements: list[Entitlement] = []

    def get_principal(self, principal_id: UUID) -> PrincipalContext | None:
        return self.principals.get(principal_id)

    def get_tenant_access(self, principal_id: UUID, tenant_id: UUID) -> TenantAccess | None:
        return self.access.get((principal_id, tenant_id))

    def get_entitlements(self, account_id: UUID, offering: str) -> tuple[Entitlement, ...]:
        return tuple(
            item
            for item in self.entitlements
            if item.account_id == account_id and item.offering == offering
        )


def setup_business() -> tuple[AuthorizationService, MemoryStore, PrincipalContext, UUID]:
    store = MemoryStore()
    principal = PrincipalContext(uuid4(), uuid4(), "BUSINESS", "ACTIVE")
    tenant_id = uuid4()
    store.principals[principal.principal_id] = principal
    store.access[(principal.principal_id, tenant_id)] = TenantAccess(
        tenant_id, principal.account_id, principal.principal_id, "OWNER", None, "ACTIVE"
    )
    store.entitlements.append(
        Entitlement(
            principal.account_id,
            tenant_id,
            "MIRROR_LITE",
            True,
            NOW - timedelta(days=1),
            None,
        )
    )
    return AuthorizationService(store), store, principal, tenant_id


def test_account_scope_comes_from_authenticated_principal() -> None:
    service, _, principal, _ = setup_business()
    assert service.require_account(principal.principal_id, principal.account_id) == principal
    with pytest.raises(AuthorizationError, match="resource unavailable"):
        service.require_account(principal.principal_id, uuid4())


def test_tenant_role_and_revocation_are_enforced() -> None:
    service, store, principal, tenant_id = setup_business()
    access = service.require_tenant(principal.principal_id, tenant_id, roles=frozenset({"OWNER"}))
    assert access.role == "OWNER"
    with pytest.raises(AuthorizationError):
        service.require_tenant(principal.principal_id, tenant_id, roles=frozenset({"ASSOCIATE"}))
    store.access[(principal.principal_id, tenant_id)] = TenantAccess(
        tenant_id, principal.account_id, principal.principal_id, "OWNER", NOW, "ACTIVE"
    )
    with pytest.raises(AuthorizationError):
        service.require_tenant(principal.principal_id, tenant_id)


def test_entitlement_requires_exact_owner_tenant_and_active_window() -> None:
    service, store, principal, tenant_id = setup_business()
    assert (
        service.require_entitlement(
            principal.principal_id, "MIRROR_LITE", tenant_id=tenant_id, now=NOW
        ).tenant_id
        == tenant_id
    )
    store.entitlements[0] = Entitlement(
        principal.account_id,
        tenant_id,
        "MIRROR_LITE",
        True,
        NOW + timedelta(seconds=1),
        None,
    )
    with pytest.raises(AuthorizationError):
        service.require_entitlement(
            principal.principal_id, "MIRROR_LITE", tenant_id=tenant_id, now=NOW
        )


def test_foreign_tenant_and_suspended_principal_receive_same_denial() -> None:
    service, store, principal, _ = setup_business()
    with pytest.raises(AuthorizationError, match="resource unavailable"):
        service.require_tenant(principal.principal_id, uuid4())
    store.principals[principal.principal_id] = PrincipalContext(
        principal.principal_id, principal.account_id, "BUSINESS", "SUSPENDED"
    )
    with pytest.raises(AuthorizationError, match="resource unavailable"):
        service.require_principal(principal.principal_id)
