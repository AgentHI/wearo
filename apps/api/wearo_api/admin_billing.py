from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import Engine, text

PaymentStatus = Literal["PAID", "PENDING", "FAILED", "OVERDUE"]
PAYMENT_STATUSES = {"PAID", "PENDING", "FAILED", "OVERDUE"}


class AdminBillingError(ValueError):
    pass


def payment_status(
    state: str, created_at: datetime, grace_days: int, now: datetime
) -> PaymentStatus:
    if state == "CONFIRMED":
        return "PAID"
    if state in {"FAILED", "REFUNDED"}:
        return "FAILED"
    return "OVERDUE" if created_at + timedelta(days=grace_days) < now else "PENDING"


class PostgresAdminBilling:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list(self, status: str | None = None) -> dict[str, object]:
        wanted = status.upper() if status else None
        if wanted and wanted not in PAYMENT_STATUSES:
            raise AdminBillingError("Unsupported payment status.")
        now = datetime.now(UTC)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT o.payment_order_id, o.tenant_id, o.state, o.created_at,
                              o.amount_minor, o.currency, p.display_name AS organization_name,
                              p.legal_name, p.billing_email, p.billing_phone,
                              p.billing_address, p.tax_identifier AS gstin,
                              r.provider_payment_id, r.issued_at AS payment_date,
                              r.tokens_credited, i.invoice_id, i.invoice_number,
                              i.subtotal_minor, i.tax_minor, i.status AS invoice_status,
                              COALESCE(price.payment_grace_days, 7) AS grace_days
                       FROM payment_orders o
                       JOIN business_profiles p ON p.tenant_id=o.tenant_id
                                                 AND p.account_id=o.account_id
                       LEFT JOIN payment_receipts r ON r.payment_order_id=o.payment_order_id
                       LEFT JOIN invoices i ON i.payment_order_id=o.payment_order_id
                       LEFT JOIN business_subscriptions s ON s.tenant_id=o.tenant_id
                       LEFT JOIN LATERAL (
                         SELECT payment_grace_days FROM platform_pricing_settings ps
                         WHERE ps.plan_code=s.plan_code
                           AND (ps.business_type IS NULL OR ps.business_type=p.operating_profile)
                           AND ps.effective_from <= o.created_at
                         ORDER BY ps.business_type NULLS LAST, ps.effective_from DESC LIMIT 1
                       ) price ON true
                       ORDER BY o.created_at DESC"""
                )
            ).mappings()
            items: list[dict[str, object]] = []
            for row in rows:
                item = dict(row)
                derived = payment_status(
                    str(item.pop("state")),
                    cast(datetime, item["created_at"]),
                    int(item.pop("grace_days")),
                    now,
                )
                item["payment_status"] = derived
                item["total_payable_minor"] = item["amount_minor"]
                if wanted is None or derived == wanted:
                    items.append(item)
            outstanding = [
                item for item in items if item["payment_status"] in {"PENDING", "OVERDUE"}
            ]
            return {
                "summary": {
                    "transactions": len(items),
                    "outstanding": len(outstanding),
                    "overdue": sum(item["payment_status"] == "OVERDUE" for item in items),
                    "outstanding_minor": sum(
                        cast(int, item["amount_minor"]) for item in outstanding
                    ),
                    "currency": "INR",
                },
                "items": items,
            }

    def invoice(self, invoice_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT i.*, r.provider_payment_id, r.issued_at AS payment_date
                       FROM invoices i
                       LEFT JOIN payment_receipts r ON r.payment_order_id=i.payment_order_id
                       WHERE i.invoice_id=:invoice"""
                    ),
                    {"invoice": invoice_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AdminBillingError("Invoice not found.")
        return dict(row)
