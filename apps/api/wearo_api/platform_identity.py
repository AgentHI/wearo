from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import Engine, text

Audience = Literal["CONSUMER", "BUSINESS"]


class PlatformIdentityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OfferingAccess:
    code: str
    name: str
    launch_url: str


@dataclass(frozen=True)
class PlatformContext:
    principal_id: UUID
    account_id: UUID
    tenant_id: UUID | None
    audience: Audience
    wallet_id: UUID | None
    billing_account_id: UUID
    offerings: tuple[OfferingAccess, ...]


OFFERINGS: dict[str, tuple[str, str, frozenset[Audience]]] = {
    "SHOP": ("Wearo Shop", "/app/", frozenset({"CONSUMER", "BUSINESS"})),
    "BUSINESS": ("Wearo Studio", "/business/dashboard", frozenset({"BUSINESS"})),
    "MIRROR_LITE": ("Wearo Mirror", "/business/mirror", frozenset({"BUSINESS"})),
}


def offering_access(code: str, audience: Audience) -> OfferingAccess:
    definition = OFFERINGS.get(code)
    if definition is None or audience not in definition[2]:
        raise PlatformIdentityError("OFFERING_UNAVAILABLE", "Offering is unavailable.")
    return OfferingAccess(code=code, name=definition[0], launch_url=definition[1])


class PostgresPlatformIdentity:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def context(
        self,
        principal_id: UUID,
        account_id: UUID,
        audience: Audience,
        *,
        tenant_id: UUID | None = None,
    ) -> PlatformContext:
        current = datetime.now(UTC)
        with self.engine.connect() as connection:
            principal = (
                connection.execute(
                    text(
                        """
                    SELECT p.principal_type, p.status, a.status AS account_status
                    FROM principals p JOIN accounts a ON a.account_id = p.account_id
                    WHERE p.principal_id = :principal AND p.account_id = :account
                    """
                    ),
                    {"principal": principal_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if (
                principal is None
                or principal["status"] != "ACTIVE"
                or principal["account_status"] != "ACTIVE"
                or principal["principal_type"] != audience
            ):
                raise PlatformIdentityError("PLATFORM_CONTEXT_UNAVAILABLE", "Context unavailable.")
            if audience == "BUSINESS":
                membership = connection.execute(
                    text(
                        """
                        SELECT 1 FROM tenant_memberships m
                        JOIN business_tenants t
                          ON t.tenant_id = m.tenant_id AND t.account_id = m.account_id
                        WHERE m.principal_id = :principal AND m.account_id = :account
                          AND m.tenant_id = :tenant AND m.revoked_at IS NULL
                          AND t.status = 'ACTIVE'
                        """
                    ),
                    {"principal": principal_id, "account": account_id, "tenant": tenant_id},
                ).one_or_none()
                if membership is None:
                    raise PlatformIdentityError(
                        "PLATFORM_CONTEXT_UNAVAILABLE", "Context unavailable."
                    )
            rows = connection.execute(
                text(
                    """
                    SELECT offering FROM offering_entitlements
                    WHERE account_id = :account
                      AND tenant_id IS NOT DISTINCT FROM :tenant
                      AND enabled AND effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY offering
                    """
                ),
                {"account": account_id, "tenant": tenant_id, "now": current},
            )
            enabled = tuple(row[0] for row in rows)
            wallet_id = connection.execute(
                text("SELECT wallet_id FROM wallets WHERE account_id = :account"),
                {"account": account_id},
            ).scalar_one_or_none()
        accessible = tuple(offering_access(code, audience) for code in enabled if code in OFFERINGS)
        return PlatformContext(
            principal_id=principal_id,
            account_id=account_id,
            tenant_id=tenant_id,
            audience=audience,
            wallet_id=wallet_id,
            billing_account_id=account_id,
            offerings=accessible,
        )

    def business_workspaces(
        self, principal_id: UUID, account_id: UUID
    ) -> tuple[dict[str, object], ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT t.tenant_id, t.slug, m.role,
                           COALESCE(p.display_name, p.legal_name, t.slug) AS name
                    FROM tenant_memberships m
                    JOIN business_tenants t
                      ON t.tenant_id = m.tenant_id AND t.account_id = m.account_id
                    JOIN principals principal
                      ON principal.principal_id = m.principal_id
                     AND principal.account_id = m.account_id
                    JOIN accounts account ON account.account_id = m.account_id
                    LEFT JOIN business_profiles p
                      ON p.tenant_id = t.tenant_id AND p.account_id = t.account_id
                    WHERE m.principal_id = :principal AND m.account_id = :account
                      AND m.revoked_at IS NULL AND t.status = 'ACTIVE'
                      AND principal.status = 'ACTIVE' AND account.status = 'ACTIVE'
                    ORDER BY name, t.tenant_id
                    """
                ),
                {"principal": principal_id, "account": account_id},
            ).mappings()
            return tuple(dict(row) for row in rows)
