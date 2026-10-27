from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .admin_organizations import ADMIN_ACTOR_ID, BUSINESS_TYPES


class AdminPricingError(ValueError):
    pass


@dataclass(frozen=True)
class PricingSnapshot:
    version: str
    amount_minor: int


def effective_purchase(snapshots: tuple[PricingSnapshot, ...], version: str) -> PricingSnapshot:
    return next(snapshot for snapshot in snapshots if snapshot.version == version)


class PostgresAdminPricing:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def current(self) -> dict[str, object]:
        now = datetime.now(UTC)
        with self.engine.connect() as connection:
            settings = connection.execute(
                text(
                    """SELECT * FROM platform_pricing_settings
                    WHERE effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY business_type NULLS FIRST, plan_code"""
                ),
                {"now": now},
            ).mappings()
            packs = connection.execute(
                text(
                    """SELECT pack_id, code, purchased_tokens, promo_tokens, amount_minor,
                              currency, tax_rate_basis_points, discount_basis_points,
                              business_type, effective_from
                    FROM token_packs WHERE effective_from <= :now
                      AND (effective_until IS NULL OR effective_until > :now)
                    ORDER BY amount_minor, code"""
                ),
                {"now": now},
            ).mappings()
            return {
                "settings": [dict(row) for row in settings],
                "token_packages": [dict(row) for row in packs],
            }

    def publish_settings(self, values: dict[str, object], reason: str) -> dict[str, object]:
        explanation = reason.strip()
        plan_code = str(values["plan_code"]).strip().upper()
        business_type = (
            str(values["business_type"]).strip().upper() if values.get("business_type") else None
        )
        if (
            not explanation
            or not plan_code
            or (business_type and business_type not in BUSINESS_TYPES)
        ):
            raise AdminPricingError("Valid pricing values and a reason are required.")
        now, pricing_id = datetime.now(UTC), uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE platform_pricing_settings SET effective_until=:now, updated_at=:now
                    WHERE plan_code=:plan AND business_type IS NOT DISTINCT FROM :business_type
                      AND effective_until IS NULL"""
                ),
                {"now": now, "plan": plan_code, "business_type": business_type},
            )
            connection.execute(
                text(
                    """INSERT INTO platform_pricing_settings
                    (pricing_id, plan_code, business_type, monthly_fee_minor,
                     try_on_token_cost, free_trial_tokens, trial_duration_days,
                     payment_grace_days, gst_basis_points, effective_from)
                    VALUES (:id, :plan, :business_type, :monthly_fee, :try_on_cost,
                            :trial_tokens, :trial_days, :grace_days, :gst, :now)"""
                ),
                {
                    "id": pricing_id,
                    "plan": plan_code,
                    "business_type": business_type,
                    "monthly_fee": values["monthly_fee_minor"],
                    "try_on_cost": values["try_on_token_cost"],
                    "trial_tokens": values["free_trial_tokens"],
                    "trial_days": values["trial_duration_days"],
                    "grace_days": values["payment_grace_days"],
                    "gst": values["gst_basis_points"],
                    "now": now,
                },
            )
            self._audit(connection, "ADMIN_PRICING_PUBLISHED", explanation, pricing_id, values, now)
        return {"pricing_id": pricing_id, "effective_from": now}

    def publish_package(self, values: dict[str, object], reason: str) -> dict[str, object]:
        explanation = reason.strip()
        code = str(values["code"]).strip().upper()
        business_type = (
            str(values["business_type"]).strip().upper() if values.get("business_type") else None
        )
        if not explanation or not code or (business_type and business_type not in BUSINESS_TYPES):
            raise AdminPricingError("Valid package values and a reason are required.")
        now, pack_id = datetime.now(UTC), uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE token_packs SET effective_until=:now, updated_at=:now
                    WHERE code=:code AND business_type IS NOT DISTINCT FROM :business_type
                      AND effective_until IS NULL"""
                ),
                {"now": now, "code": code, "business_type": business_type},
            )
            connection.execute(
                text(
                    """INSERT INTO token_packs
                    (pack_id, code, purchased_tokens, promo_tokens, amount_minor, currency,
                     tax_rate_basis_points, discount_basis_points, business_type, effective_from)
                    VALUES (:id, :code, :purchased, :promo, :amount, 'INR', :gst,
                            :discount, :business_type, :now)"""
                ),
                {
                    "id": pack_id,
                    "code": code,
                    "purchased": values["purchased_tokens"],
                    "promo": values["promo_tokens"],
                    "amount": values["amount_minor"],
                    "gst": values["gst_basis_points"],
                    "discount": values["discount_basis_points"],
                    "business_type": business_type,
                    "now": now,
                },
            )
            self._audit(
                connection, "ADMIN_TOKEN_PACKAGE_PUBLISHED", explanation, pack_id, values, now
            )
        return {"pack_id": pack_id, "effective_from": now}

    @staticmethod
    def _audit(
        connection: object,
        action: str,
        reason: str,
        target: UUID,
        values: dict[str, object],
        now: datetime,
    ) -> None:
        connection.execute(  # type: ignore[attr-defined]
            text(
                """INSERT INTO audit_events
                (audit_event_id, actor_type, actor_id, action, target_type, target_id,
                 reason, after_summary, occurred_at)
                VALUES (:event, 'ADMIN', :actor, :action, 'PLATFORM_PRICING', :target,
                        :reason, CAST(:after AS jsonb), :now)"""
            ),
            {
                "event": uuid4(),
                "actor": ADMIN_ACTOR_ID,
                "action": action,
                "target": target,
                "reason": reason,
                "after": json.dumps(values, default=str),
                "now": now,
            },
        )
