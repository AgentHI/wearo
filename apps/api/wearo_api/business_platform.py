from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .tenant_scope import TenantRole, TenantScopeError, require_tenant_scope

OperatingProfile = Literal[
    "BOUTIQUE", "CLOTHING_RETAILER", "JEWELLERY_RETAILER", "ENTERPRISE_CHAIN", "OTHER"
]


class BusinessPlatformError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProfileRecommendation:
    catalog_label: str
    eligible_offerings: tuple[str, ...]
    required_catalog_fields: tuple[str, ...]


RECOMMENDATIONS: dict[OperatingProfile, ProfileRecommendation] = {
    "BOUTIQUE": ProfileRecommendation("Designs", ("BUSINESS",), ("title", "price", "size")),
    "CLOTHING_RETAILER": ProfileRecommendation(
        "Products", ("BUSINESS", "SHOP"), ("title", "price", "size", "brand")
    ),
    "JEWELLERY_RETAILER": ProfileRecommendation(
        "Jewellery", (), ("title", "price", "material", "dimensions")
    ),
    "ENTERPRISE_CHAIN": ProfileRecommendation(
        "Products", ("BUSINESS", "MIRROR_LITE"), ("title", "price", "outlet_code")
    ),
    "OTHER": ProfileRecommendation("Items", ("BUSINESS",), ("title", "price")),
}

ACTION_EXPLANATIONS: dict[str, str] = {
    "TRY_ON": "Generate one virtual try-on preview.",
    "IMAGE_VARIANT": "Generate one additional image variant from an existing request.",
    "PREVIEW_3D": "Generate one eligible 3D product preview.",
    "OTHER": "Other billable actions use the rate displayed before confirmation.",
}


def recommendation_for(profile: OperatingProfile) -> ProfileRecommendation:
    return RECOMMENDATIONS[profile]


def estimated_actions(tokens: int, token_cost: int) -> int:
    if tokens < 0 or token_cost <= 0:
        raise BusinessPlatformError("INVALID_TOKEN_ESTIMATE", "Token values are invalid.")
    return tokens // token_cost


class PostgresBusinessPlatform:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _require_member(
        connection: Connection, principal_id: UUID, tenant_id: UUID, *, owner: bool = False
    ) -> UUID:
        roles: frozenset[TenantRole] = (
            frozenset({"OWNER"}) if owner else frozenset({"OWNER", "ASSOCIATE"})
        )
        try:
            return require_tenant_scope(connection, principal_id, tenant_id, roles=roles).account_id
        except TenantScopeError:
            raise BusinessPlatformError(
                "BUSINESS_RESOURCE_UNAVAILABLE", "Resource unavailable."
            ) from None

    def pricing(self) -> tuple[dict[str, object], ...]:
        current = datetime.now(UTC)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT action_code, token_cost, effective_from, effective_until
                    FROM price_versions
                    WHERE effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY action_code
                    """
                ),
                {"now": current},
            ).mappings()
            published = {row["action_code"]: dict(row) for row in rows}
        schedule: list[dict[str, object]] = []
        for action_code, explanation in ACTION_EXPLANATIONS.items():
            rate = published.get(action_code)
            schedule.append(
                {
                    "action_code": action_code,
                    "description": explanation,
                    "status": "PUBLISHED" if rate else "UNPUBLISHED",
                    "token_cost": rate["token_cost"] if rate else None,
                    "effective_from": rate["effective_from"] if rate else None,
                    "effective_until": rate["effective_until"] if rate else None,
                }
            )
        for action_code, rate in published.items():
            if action_code not in ACTION_EXPLANATIONS:
                schedule.append(
                    {
                        **rate,
                        "description": "Billable product action.",
                        "status": "PUBLISHED",
                    }
                )
        return tuple(schedule)

    def overview(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        current = datetime.now(UTC)
        with self.engine.connect() as connection:
            account_id = self._require_member(connection, principal_id, tenant_id)
            profile = (
                connection.execute(
                    text(
                        """
                    SELECT legal_name, display_name, operating_profile, jurisdiction
                    FROM business_profiles
                    WHERE tenant_id = :tenant AND account_id = :account
                    """
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            entitlements = tuple(
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT offering FROM offering_entitlements
                        WHERE account_id = :account AND tenant_id = :tenant AND enabled
                          AND effective_from <= :now
                          AND (effective_until IS NULL OR effective_until > :now)
                        ORDER BY offering
                        """
                    ),
                    {"account": account_id, "tenant": tenant_id, "now": current},
                )
            )
            balance = int(
                connection.execute(
                    text(
                        "SELECT COALESCE(sum(amount), 0) FROM ledger_entries "
                        "WHERE account_id = :account"
                    ),
                    {"account": account_id},
                ).scalar_one()
            )
            used = int(
                connection.execute(
                    text(
                        """
                    SELECT COALESCE(-sum(amount), 0) FROM ledger_entries
                    WHERE account_id = :account AND entry_type = 'DEBIT' AND amount < 0
                    """
                    ),
                    {"account": account_id},
                ).scalar_one()
            )
            allowance = (
                connection.execute(
                    text(
                        """
                    SELECT default_try_on_limit, period FROM business_allowance_policies
                    WHERE tenant_id = :tenant AND account_id = :account
                    """
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            profile_change = (
                connection.execute(
                    text(
                        """SELECT request_id, requested_profile, reason, state, created_at
                    FROM business_profile_change_requests
                    WHERE tenant_id=:tenant AND account_id=:account AND state='OPEN'"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
        profile_json = dict(profile) if profile else None
        recommendation = None
        if profile:
            selected = recommendation_for(profile["operating_profile"])
            recommendation = {
                "catalog_label": selected.catalog_label,
                "eligible_offerings": selected.eligible_offerings,
                "required_catalog_fields": selected.required_catalog_fields,
            }
        return {
            "tenant_id": tenant_id,
            "account_id": account_id,
            "profile": profile_json,
            "recommendation": recommendation,
            "enabled_offerings": entitlements,
            "wallet": {"unit": "WEARO_TOKEN", "balance": balance, "used": used},
            "allowance": dict(allowance) if allowance else None,
            "profile_change_request": dict(profile_change) if profile_change else None,
        }

    def customer_experience_settings(self, principal_id: UUID, tenant_id: UUID) -> dict[str, int]:
        with self.engine.connect() as connection:
            account_id = self._require_member(connection, principal_id, tenant_id, owner=True)
            row = (
                connection.execute(
                    text(
                        """SELECT image_retention_days, profile_deletion_hours
                    FROM business_profiles
                    WHERE tenant_id = :tenant AND account_id = :account"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise BusinessPlatformError("BUSINESS_RESOURCE_UNAVAILABLE", "Resource unavailable.")
        return {
            "image_retention_days": int(row["image_retention_days"]),
            "profile_deletion_hours": int(row["profile_deletion_hours"]),
        }

    def update_customer_experience_settings(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        image_retention_days: int,
        profile_deletion_hours: int,
        reason: str,
    ) -> dict[str, int]:
        if not 1 <= image_retention_days <= 30:
            raise BusinessPlatformError(
                "INVALID_RETENTION", "Image retention must be between 1 and 30 days."
            )
        if not 1 <= profile_deletion_hours <= 24:
            raise BusinessPlatformError(
                "INVALID_DELETION_WINDOW", "Profile deletion must be between 1 and 24 hours."
            )
        explanation = reason.strip()
        if not explanation or len(explanation) > 500:
            raise BusinessPlatformError("CHANGE_REASON_REQUIRED", "A change reason is required.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            account_id = self._require_member(connection, principal_id, tenant_id, owner=True)
            before = (
                connection.execute(
                    text(
                        """SELECT image_retention_days, profile_deletion_hours
                    FROM business_profiles WHERE tenant_id=:tenant AND account_id=:account
                    FOR UPDATE"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if before is None:
                raise BusinessPlatformError(
                    "BUSINESS_RESOURCE_UNAVAILABLE", "Resource unavailable."
                )
            connection.execute(
                text(
                    """UPDATE business_profiles
                    SET image_retention_days=:retention, profile_deletion_hours=:deletion,
                        updated_at=:now
                    WHERE tenant_id=:tenant AND account_id=:account"""
                ),
                {
                    "retention": image_retention_days,
                    "deletion": profile_deletion_hours,
                    "now": now,
                    "tenant": tenant_id,
                    "account": account_id,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO audit_events
                    (audit_event_id, account_id, tenant_id, actor_type, actor_id, action,
                     target_type, target_id, reason, before_summary, after_summary, occurred_at)
                    VALUES (:event, :account, :tenant, 'PRINCIPAL', :actor,
                            'CUSTOMER_EXPERIENCE_SETTINGS_UPDATED', 'BUSINESS_TENANT', :tenant,
                            :reason, CAST(:before AS jsonb), CAST(:after AS jsonb), :now)"""
                ),
                {
                    "event": uuid4(),
                    "account": account_id,
                    "tenant": tenant_id,
                    "actor": principal_id,
                    "reason": explanation,
                    "before": json.dumps(dict(before)),
                    "after": json.dumps(
                        {
                            "image_retention_days": image_retention_days,
                            "profile_deletion_hours": profile_deletion_hours,
                        }
                    ),
                    "now": now,
                },
            )
        return {
            "image_retention_days": image_retention_days,
            "profile_deletion_hours": profile_deletion_hours,
        }

    def request_profile_change(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        requested_profile: OperatingProfile,
        reason: str,
    ) -> dict[str, object]:
        explanation = reason.strip()
        if not explanation or len(explanation) > 500:
            raise BusinessPlatformError("CHANGE_REASON_REQUIRED", "A change reason is required.")
        if requested_profile not in RECOMMENDATIONS:
            raise BusinessPlatformError("INVALID_OPERATING_PROFILE", "Select a supported profile.")
        now, request_id = datetime.now(UTC), uuid4()
        with self.engine.begin() as connection:
            account_id = self._require_member(connection, principal_id, tenant_id, owner=True)
            current = connection.execute(
                text(
                    """SELECT operating_profile FROM business_profiles
                    WHERE tenant_id=:tenant AND account_id=:account FOR UPDATE"""
                ),
                {"tenant": tenant_id, "account": account_id},
            ).scalar_one_or_none()
            if current is None:
                raise BusinessPlatformError(
                    "BUSINESS_RESOURCE_UNAVAILABLE", "Resource unavailable."
                )
            if current == requested_profile:
                raise BusinessPlatformError(
                    "PROFILE_CHANGE_NOT_REQUIRED", "The requested profile is already active."
                )
            existing = (
                connection.execute(
                    text(
                        """SELECT request_id, requested_profile, reason, state, created_at
                    FROM business_profile_change_requests
                    WHERE tenant_id=:tenant AND account_id=:account AND state='OPEN'"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                return dict(existing)
            row = (
                connection.execute(
                    text(
                        """INSERT INTO business_profile_change_requests
                    (request_id, tenant_id, account_id, requested_by_principal_id,
                     requested_profile, reason, state, created_at)
                    VALUES (:request, :tenant, :account, :principal, :profile,
                            :reason, 'OPEN', :now)
                    RETURNING request_id, requested_profile, reason, state, created_at"""
                    ),
                    {
                        "request": request_id,
                        "tenant": tenant_id,
                        "account": account_id,
                        "principal": principal_id,
                        "profile": requested_profile,
                        "reason": explanation,
                        "now": now,
                    },
                )
                .mappings()
                .one()
            )
            connection.execute(
                text(
                    """INSERT INTO audit_events
                    (account_id, tenant_id, actor_type, actor_id, action, target_type,
                     target_id, reason, occurred_at)
                    VALUES (:account, :tenant, 'PRINCIPAL', :principal,
                            'OPERATING_PROFILE_CHANGE_REQUESTED', 'BUSINESS_PROFILE',
                            :tenant, :reason, :now)"""
                ),
                {
                    "account": account_id,
                    "tenant": tenant_id,
                    "principal": principal_id,
                    "reason": explanation,
                    "now": now,
                },
            )
            return dict(row)
