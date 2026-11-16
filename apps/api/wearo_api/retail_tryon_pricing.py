from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, text

from .admin_organizations import ADMIN_ACTOR_ID


class RetailTryOnPricingError(ValueError):
    pass


def tokens_for_price_minor(price_minor: int) -> int:
    if price_minor <= 0 or price_minor % 20:
        raise RetailTryOnPricingError("Price must be a positive multiple of ₹0.20.")
    return price_minor // 20


def package_values(
    minimum_amount_minor: int, tokens_per_tryon: int, gst_basis_points: int = 1800
) -> dict[str, int]:
    total_tokens = tokens_for_price_minor(minimum_amount_minor)
    if tokens_per_tryon <= 0:
        raise RetailTryOnPricingError("A published try-on token rate is required.")
    if not 0 <= gst_basis_points <= 10_000:
        raise RetailTryOnPricingError("GST rate must be between 0% and 100%.")
    tax_minor = round(minimum_amount_minor * gst_basis_points / 10_000)
    return {
        "total_tokens": total_tokens,
        "number_of_tryons": total_tokens // tokens_per_tryon,
        "tax_minor": tax_minor,
        "final_amount_minor": minimum_amount_minor + tax_minor,
    }


class PostgresRetailTryOnPricing:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def current(self) -> dict[str, object] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """SELECT retail_price_id, price_minor, tokens_per_tryon, currency,
                              effective_from, reason
                       FROM retail_tryon_prices
                       WHERE effective_from <= now() AND effective_until IS NULL
                       ORDER BY effective_from DESC LIMIT 1"""
                )
            ).mappings().one_or_none()
        return dict(row) if row else None

    def history(self) -> dict[str, object]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT retail_price_id, price_minor, tokens_per_tryon, currency,
                              effective_from, effective_until, reason
                       FROM retail_tryon_prices ORDER BY effective_from DESC LIMIT 50"""
                )
            ).mappings()
            history = [dict(row) for row in rows]
        return {"current": self.current(), "history": history, "packages": self.packages()}

    def packages(self) -> list[dict[str, object]]:
        current = self.current()
        if current is None:
            return []
        tokens_per_tryon = int(current["tokens_per_tryon"])
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT retail_package_id, name, minimum_amount_minor, gst_basis_points, currency,
                              created_at
                       FROM retail_tryon_packages WHERE active=true
                       ORDER BY minimum_amount_minor, name"""
                )
            ).mappings()
            return [
                {
                    **dict(row),
                    **package_values(
                        int(row["minimum_amount_minor"]),
                        tokens_per_tryon,
                        int(row["gst_basis_points"]),
                    ),
                }
                for row in rows
            ]

    def create_package(
        self, name: str, minimum_amount_minor: int, gst_basis_points: int, reason: str
    ) -> dict[str, object]:
        package_name, explanation = name.strip(), reason.strip()
        if not package_name or len(package_name) > 80:
            raise RetailTryOnPricingError("Package name must contain 1 to 80 characters.")
        if not explanation:
            raise RetailTryOnPricingError("A reason for creating the package is required.")
        current = self.current()
        if current is None:
            raise RetailTryOnPricingError("Publish a retail try-on price before creating packages.")
        calculated = package_values(
            minimum_amount_minor, int(current["tokens_per_tryon"]), gst_basis_points
        )
        now, package_id = datetime.now(UTC), uuid4()
        summary = {
            "name": package_name,
            "minimum_amount_minor": minimum_amount_minor,
            "gst_basis_points": gst_basis_points,
            **calculated,
        }
        with self.engine.begin() as connection:
            exists = connection.execute(
                text(
                    "SELECT 1 FROM retail_tryon_packages "
                    "WHERE lower(name)=lower(:name) AND active=true"
                ),
                {"name": package_name},
            ).scalar_one_or_none()
            if exists:
                raise RetailTryOnPricingError("A package with this name already exists.")
            connection.execute(
                text(
                    """INSERT INTO retail_tryon_packages
                       (retail_package_id, name, minimum_amount_minor, gst_basis_points,
                        currency, reason)
                       VALUES (:id, :name, :amount, :gst, 'INR', :reason)"""
                ),
                {
                    "id": package_id,
                    "name": package_name,
                    "amount": minimum_amount_minor,
                    "gst": gst_basis_points,
                    "reason": explanation,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO audit_events
                       (audit_event_id, actor_type, actor_id, action, target_type,
                        target_id, reason, after_summary, occurred_at)
                       VALUES (:event, 'ADMIN', :actor, 'ADMIN_RETAIL_TRYON_PACKAGE_CREATED',
                               'RETAIL_TRYON_PACKAGE', :target, :reason,
                               CAST(:summary AS jsonb), :now)"""
                ),
                {
                    "event": uuid4(),
                    "actor": ADMIN_ACTOR_ID,
                    "target": package_id,
                    "reason": explanation,
                    "summary": json.dumps(summary),
                    "now": now,
                },
            )
        return {"retail_package_id": package_id, "currency": "INR", **summary}

    def update_package(
        self, package_id: object, name: str, minimum_amount_minor: int,
        gst_basis_points: int, reason: str
    ) -> dict[str, object]:
        package_name, explanation = name.strip(), reason.strip()
        if not package_name or len(package_name) > 80:
            raise RetailTryOnPricingError("Package name must contain 1 to 80 characters.")
        if not explanation:
            raise RetailTryOnPricingError("A reason for editing the package is required.")
        current = self.current()
        if current is None:
            raise RetailTryOnPricingError("Publish a retail try-on price before editing packages.")
        calculated = package_values(
            minimum_amount_minor, int(current["tokens_per_tryon"]), gst_basis_points
        )
        now = datetime.now(UTC)
        summary = {"name": package_name, "minimum_amount_minor": minimum_amount_minor, "gst_basis_points": gst_basis_points, **calculated}
        with self.engine.begin() as connection:
            before = connection.execute(
                text(
                    """SELECT name, minimum_amount_minor, gst_basis_points FROM retail_tryon_packages
                       WHERE retail_package_id=:id AND active=true FOR UPDATE"""
                ),
                {"id": package_id},
            ).mappings().one_or_none()
            if before is None:
                raise RetailTryOnPricingError("Active package not found.")
            duplicate = connection.execute(
                text(
                    """SELECT 1 FROM retail_tryon_packages
                       WHERE lower(name)=lower(:name) AND retail_package_id<>:id AND active=true"""
                ),
                {"name": package_name, "id": package_id},
            ).scalar_one_or_none()
            if duplicate:
                raise RetailTryOnPricingError("A package with this name already exists.")
            connection.execute(
                text(
                    """UPDATE retail_tryon_packages
                       SET name=:name, minimum_amount_minor=:amount, gst_basis_points=:gst,
                           reason=:reason, updated_at=:now
                       WHERE retail_package_id=:id"""
                ),
                {"id": package_id, "name": package_name, "amount": minimum_amount_minor, "gst": gst_basis_points, "reason": explanation, "now": now},
            )
            self._audit_package(connection, "ADMIN_RETAIL_TRYON_PACKAGE_UPDATED", package_id, explanation, summary, now, dict(before))
        return {"retail_package_id": package_id, "currency": "INR", **summary}

    def delete_package(self, package_id: object, reason: str) -> dict[str, object]:
        explanation = reason.strip()
        if not explanation:
            raise RetailTryOnPricingError("A reason for deleting the package is required.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            before = connection.execute(
                text(
                    """UPDATE retail_tryon_packages SET active=false, reason=:reason, updated_at=:now
                       WHERE retail_package_id=:id AND active=true
                       RETURNING name, minimum_amount_minor"""
                ),
                {"id": package_id, "reason": explanation, "now": now},
            ).mappings().one_or_none()
            if before is None:
                raise RetailTryOnPricingError("Active package not found.")
            self._audit_package(connection, "ADMIN_RETAIL_TRYON_PACKAGE_DELETED", package_id, explanation, {"active": False}, now, dict(before))
        return {"retail_package_id": package_id, "deleted": True}

    @staticmethod
    def _audit_package(
        connection: object,
        action: str,
        package_id: object,
        reason: str,
        after: dict[str, object],
        now: datetime,
        before: dict[str, object] | None = None,
    ) -> None:
        connection.execute(  # type: ignore[attr-defined]
            text(
                """INSERT INTO audit_events
                   (audit_event_id, actor_type, actor_id, action, target_type,
                    target_id, reason, before_summary, after_summary, occurred_at)
                   VALUES (:event, 'ADMIN', :actor, :action, 'RETAIL_TRYON_PACKAGE',
                           :target, :reason, CAST(:before AS jsonb), CAST(:after AS jsonb), :now)"""
            ),
            {"event": uuid4(), "actor": ADMIN_ACTOR_ID, "action": action, "target": package_id, "reason": reason, "before": json.dumps(before) if before else None, "after": json.dumps(after), "now": now},
        )

    def publish(self, price_minor: int, reason: str) -> dict[str, object]:
        explanation = reason.strip()
        if not explanation:
            raise RetailTryOnPricingError("A reason for the price decision is required.")
        tokens = tokens_for_price_minor(price_minor)
        now, retail_price_id = datetime.now(UTC), uuid4()
        summary = {
            "price_minor": price_minor,
            "tokens_per_tryon": tokens,
            "currency": "INR",
            "formula": "(try-on price in INR × 10) ÷ 2",
        }
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE retail_tryon_prices SET effective_until=:now
                       WHERE effective_until IS NULL"""
                ),
                {"now": now},
            )
            connection.execute(
                text(
                    """INSERT INTO retail_tryon_prices
                       (retail_price_id, price_minor, tokens_per_tryon, currency,
                        reason, effective_from)
                       VALUES (:id, :price, :tokens, 'INR', :reason, :now)"""
                ),
                {
                    "id": retail_price_id,
                    "price": price_minor,
                    "tokens": tokens,
                    "reason": explanation,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO audit_events
                       (audit_event_id, actor_type, actor_id, action, target_type,
                        target_id, reason, after_summary, occurred_at)
                       VALUES (:event, 'ADMIN', :actor, 'ADMIN_RETAIL_TRYON_PRICE_PUBLISHED',
                               'RETAIL_TRYON_PRICE', :target, :reason,
                               CAST(:summary AS jsonb), :now)"""
                ),
                {
                    "event": uuid4(),
                    "actor": ADMIN_ACTOR_ID,
                    "target": retail_price_id,
                    "reason": explanation,
                    "summary": json.dumps(summary),
                    "now": now,
                },
            )
        return {"retail_price_id": retail_price_id, "effective_from": now, **summary}
