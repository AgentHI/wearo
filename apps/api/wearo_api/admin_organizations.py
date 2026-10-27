from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Engine, text

from .tryon_authorization import BusinessTryOnStatus

BUSINESS_TYPES = frozenset(
    {"BOUTIQUE", "CLOTHING_RETAILER", "JEWELLERY_RETAILER", "ENTERPRISE_CHAIN", "OTHER"}
)
OPERATIONAL_STATUSES = frozenset({"ACTIVE", "PAUSED", "CANCELLED", "SUSPENDED", "CLOSED"})


class AdminOrganizationError(ValueError):
    pass


OrganizationAction = Literal["ACTIVATE", "PAUSE", "RESUME", "DEACTIVATE"]
ADMIN_ACTOR_ID = uuid5(NAMESPACE_URL, "https://wearo.ai/admin/super-admin")


def organization_status_after(
    current: str, action: OrganizationAction
) -> BusinessTryOnStatus:
    transitions: dict[OrganizationAction, BusinessTryOnStatus] = {
        "ACTIVATE": "ACTIVE",
        "PAUSE": "PAUSED",
        "RESUME": "ACTIVE",
        "DEACTIVATE": "CANCELLED",
    }
    target = transitions[action]
    if action == "PAUSE" and current != "ACTIVE":
        raise AdminOrganizationError("Only an active organization can be paused.")
    if action == "RESUME" and current != "PAUSED":
        raise AdminOrganizationError("Only a paused organization can be resumed.")
    return target


class PostgresAdminOrganizations:
    """Read-only platform-admin view over the canonical business onboarding tables."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    SELECT_BASE = """
            SELECT t.tenant_id, t.account_id, p.display_name AS organization_name,
                   p.operating_profile AS business_type, t.created_at AS onboarding_date,
                   CASE
                     WHEN plan.cancelled_at IS NOT NULL THEN 'CANCELLED'
                     WHEN plan.plan_code IS NOT NULL THEN 'ACTIVE'
                     ELSE 'UNASSIGNED'
                   END AS subscription_status,
                   CASE WHEN t.status = 'ACTIVE' THEN t.try_on_status ELSE t.status END
                     AS operational_status,
                   t.slug, p.legal_name, p.jurisdiction, p.billing_email,
                   p.billing_phone, p.website_url,
                   plan.plan_code
            FROM business_tenants t
            JOIN business_profiles p
              ON p.tenant_id = t.tenant_id AND p.account_id = t.account_id
            LEFT JOIN LATERAL (
                SELECT pa.plan_code, pa.cancelled_at
                FROM plan_assignments pa
                WHERE pa.account_id = t.account_id AND pa.tenant_id = t.tenant_id
                  AND pa.effective_from <= now()
                  AND (pa.effective_until IS NULL OR pa.effective_until > now())
                ORDER BY pa.effective_from DESC LIMIT 1
            ) plan ON true
        """

    def list(
        self,
        *,
        search: str = "",
        business_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        normalized_type = business_type.strip().upper() if business_type else None
        normalized_status = status.strip().upper() if status else None
        if normalized_type and normalized_type not in BUSINESS_TYPES:
            raise AdminOrganizationError("Unsupported business type filter.")
        if normalized_status and normalized_status not in OPERATIONAL_STATUSES:
            raise AdminOrganizationError("Unsupported organization status filter.")
        parameters = {
            "search": f"%{search.strip()}%",
            "has_search": bool(search.strip()),
            "business_type": normalized_type,
            "status": normalized_status,
        }
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    self.SELECT_BASE
                    + """
                    WHERE (NOT :has_search OR p.display_name ILIKE :search)
                      AND (CAST(:business_type AS varchar) IS NULL
                           OR p.operating_profile = CAST(:business_type AS varchar))
                      AND (CAST(:status AS varchar) IS NULL OR
                           (CASE WHEN t.status = 'ACTIVE' THEN t.try_on_status ELSE t.status END)
                           = CAST(:status AS varchar))
                    ORDER BY p.display_name, t.tenant_id
                    """
                ),
                parameters,
            ).mappings()
            organizations = []
            for row in rows:
                organization = dict(row)
                organization.pop("account_id", None)
                organizations.append(organization)
            summary = connection.execute(
                text(
                    """
                    SELECT count(*) AS total,
                           count(*) FILTER (WHERE status='ACTIVE' AND try_on_status='ACTIVE')
                             AS active,
                           count(*) FILTER (WHERE status='ACTIVE' AND try_on_status='PAUSED')
                             AS paused
                    FROM business_tenants
                    """
                )
            ).mappings().one()
        return {"summary": dict(summary), "organizations": organizations}

    def get(self, tenant_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(self.SELECT_BASE + " WHERE t.tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).mappings().one_or_none()
            if row is None:
                raise AdminOrganizationError("Organization not found.")
            metrics = connection.execute(
                text(
                    """
                    SELECT COALESCE(sum(e.amount), 0) AS available_tokens,
                           COALESCE((SELECT sum(token_cost) FROM billable_usage_records
                                    WHERE account_id=:account AND tenant_id=:tenant), 0)
                             AS tokens_consumed,
                           COALESCE((SELECT count(*) FROM billable_usage_records
                                    WHERE account_id=:account AND tenant_id=:tenant
                                      AND action_code='TRY_ON'), 0) AS total_try_ons
                    FROM ledger_entries e
                    WHERE e.account_id=:account AND e.tenant_id=:tenant
                    """
                ),
                {"account": row["account_id"], "tenant": tenant_id},
            ).mappings().one()
            payments = connection.execute(
                text(
                    """
                    SELECT receipt_id, receipt_number, amount_minor, currency,
                           tokens_credited, issued_at
                    FROM payment_receipts WHERE account_id=:account
                    ORDER BY issued_at DESC LIMIT 20
                    """
                ),
                {"account": row["account_id"]},
            ).mappings()
        result = dict(row)
        result.update(dict(metrics))
        result["billing_status"] = (
            "CURRENT" if result["subscription_status"] == "ACTIVE" else "NO_ACTIVE_PLAN"
        )
        result["payment_history"] = [dict(payment) for payment in payments]
        result.pop("account_id", None)
        return result

    def change_status(
        self, tenant_id: UUID, action: OrganizationAction, reason: str
    ) -> dict[str, str]:
        explanation = reason.strip()
        if not explanation:
            raise AdminOrganizationError("A reason is required.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            tenant = connection.execute(
                text(
                    "SELECT account_id, try_on_status FROM business_tenants "
                    "WHERE tenant_id=:tenant FOR UPDATE"
                ),
                {"tenant": tenant_id},
            ).mappings().one_or_none()
            if tenant is None:
                raise AdminOrganizationError("Organization not found.")
            before = str(tenant["try_on_status"])
            target = organization_status_after(before, action)
            connection.execute(
                text(
                    "UPDATE business_tenants SET try_on_status=:status, updated_at=:now "
                    "WHERE tenant_id=:tenant"
                ),
                {"status": target, "now": now, "tenant": tenant_id},
            )
            self._audit(
                connection,
                account_id=tenant["account_id"],
                tenant_id=tenant_id,
                action=f"ADMIN_ORGANIZATION_{action}",
                reason=explanation,
                before={"operational_status": before},
                after={"operational_status": target},
                now=now,
            )
        return {"operational_status": target}

    def adjust_tokens(self, tenant_id: UUID, amount: int, reason: str) -> dict[str, int]:
        explanation = reason.strip()
        if not explanation:
            raise AdminOrganizationError("A reason is required.")
        if amount == 0 or abs(amount) > 1_000_000:
            raise AdminOrganizationError(
                "Token adjustment must be between -1,000,000 and 1,000,000."
            )
        now, entry_id = datetime.now(UTC), uuid4()
        with self.engine.begin() as connection:
            tenant = connection.execute(
                text("SELECT account_id FROM business_tenants WHERE tenant_id=:tenant FOR UPDATE"),
                {"tenant": tenant_id},
            ).mappings().one_or_none()
            if tenant is None:
                raise AdminOrganizationError("Organization not found.")
            balance = int(
                connection.execute(
                    text(
                        "SELECT COALESCE(sum(amount), 0) FROM ledger_entries "
                        "WHERE account_id=:account"
                    ),
                    {"account": tenant["account_id"]},
                ).scalar_one()
            )
            if balance + amount < 0:
                raise AdminOrganizationError("Token adjustment cannot make the balance negative.")
            bucket = connection.execute(
                text(
                    "SELECT bucket_id, wallet_id FROM wallet_buckets "
                    "WHERE account_id=:account AND bucket_type='PURCHASED' "
                    "ORDER BY created_at LIMIT 1 FOR UPDATE"
                ),
                {"account": tenant["account_id"]},
            ).mappings().one_or_none()
            if bucket is None:
                raise AdminOrganizationError("Organization wallet is unavailable.")
            entry_type = "CREDIT" if amount > 0 else "DEBIT"
            connection.execute(
                text(
                    """INSERT INTO ledger_entries
                    (entry_id, account_id, tenant_id, wallet_id, bucket_id, entry_type,
                     amount, operation_key)
                    VALUES (:entry, :account, :tenant, :wallet, :bucket, :entry_type,
                            :amount, :operation_key)"""
                ),
                {
                    "entry": entry_id,
                    "account": tenant["account_id"],
                    "tenant": tenant_id,
                    "wallet": bucket["wallet_id"],
                    "bucket": bucket["bucket_id"],
                    "entry_type": entry_type,
                    "amount": amount,
                    "operation_key": f"admin-adjustment:{entry_id}",
                },
            )
            self._audit(
                connection,
                account_id=tenant["account_id"],
                tenant_id=tenant_id,
                action="ADMIN_TOKEN_ADJUSTMENT",
                reason=explanation,
                before={"available_tokens": balance},
                after={"available_tokens": balance + amount, "adjustment": amount},
                now=now,
            )
        return {"available_tokens": balance + amount, "adjustment": amount}

    @staticmethod
    def _audit(
        connection: Any,
        *,
        account_id: UUID,
        tenant_id: UUID,
        action: str,
        reason: str,
        before: dict[str, object],
        after: dict[str, object],
        now: datetime,
    ) -> None:
        connection.execute(
            text(
                """INSERT INTO audit_events
                (audit_event_id, account_id, tenant_id, actor_type, actor_id, action,
                 target_type, target_id, reason, before_summary, after_summary, occurred_at)
                VALUES (:event, :account, :tenant, 'ADMIN', :actor, :action,
                        'BUSINESS_TENANT', :tenant, :reason, CAST(:before AS jsonb),
                        CAST(:after AS jsonb), :now)"""
            ),
            {
                "event": uuid4(), "account": account_id, "tenant": tenant_id,
                "actor": ADMIN_ACTOR_ID, "action": action, "reason": reason,
                "before": json.dumps(before), "after": json.dumps(after), "now": now,
            },
        )
