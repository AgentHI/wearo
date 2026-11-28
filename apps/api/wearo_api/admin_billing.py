from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import Engine, text

from .plan_usage import BUSINESS_REPORTING_TIMEZONE

PaymentStatus = Literal["PAID", "PENDING", "FAILED", "OVERDUE"]
PAYMENT_STATUSES = {"PAID", "PENDING", "FAILED", "OVERDUE"}
REPORT_PAYMENT_STATUSES = PAYMENT_STATUSES | {"REFUNDED"}
PAYMENT_AUDIENCES = {"B2C", "B2B"}


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

    def report(
        self,
        *,
        audience: str,
        date_from: date,
        date_to: date,
        status: str | None = None,
    ) -> dict[str, object]:
        wanted_audience = audience.upper()
        wanted_status = status.upper() if status else None
        if wanted_audience not in PAYMENT_AUDIENCES:
            raise AdminBillingError("Unsupported payment audience.")
        if wanted_status and wanted_status not in REPORT_PAYMENT_STATUSES:
            raise AdminBillingError("Unsupported payment status.")
        if date_from > date_to:
            raise AdminBillingError("Start date must not be after end date.")
        if (date_to - date_from).days > 366:
            raise AdminBillingError("Payment report date range cannot exceed 367 days.")

        start = datetime.combine(date_from, time.min, BUSINESS_REPORTING_TIMEZONE).astimezone(UTC)
        end = datetime.combine(
            date_to + timedelta(days=1), time.min, BUSINESS_REPORTING_TIMEZONE
        ).astimezone(UTC)
        is_b2c = wanted_audience == "B2C"
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT o.payment_order_id, o.account_id, o.tenant_id, o.state,
                              o.created_at, o.updated_at, o.amount_minor, o.currency,
                              o.provider_order_id, o.revenue_type,
                              COALESCE(o.purchased_tokens, 0)
                                + COALESCE(o.promo_tokens, 0) AS ordered_tokens,
                              receipt.receipt_id, receipt.receipt_number,
                              receipt.provider_payment_id, receipt.issued_at AS paid_at,
                              COALESCE(receipt.tokens_credited, 0) AS tokens_credited,
                              refund.updated_at AS refunded_at,
                              refund.amount_minor AS refunded_amount_minor,
                              COALESCE(refund.tokens_reversed, 0) AS tokens_reversed,
                              invoice.invoice_id, invoice.invoice_number,
                              invoice.subtotal_minor, invoice.tax_minor,
                              profile.display_name AS organization_name,
                              retail.name AS retail_package_name,
                              pack.code AS business_package_name,
                              identity.normalized_value AS customer_identity,
                              COALESCE(price.payment_grace_days, 7) AS grace_days
                       FROM payment_orders o
                       LEFT JOIN payment_receipts receipt
                         ON receipt.payment_order_id=o.payment_order_id
                       LEFT JOIN payment_refunds refund
                         ON refund.payment_order_id=o.payment_order_id
                       LEFT JOIN invoices invoice
                         ON invoice.payment_order_id=o.payment_order_id
                       LEFT JOIN business_profiles profile
                         ON profile.tenant_id=o.tenant_id AND profile.account_id=o.account_id
                       LEFT JOIN retail_tryon_packages retail
                         ON retail.retail_package_id=o.retail_package_id
                       LEFT JOIN token_packs pack ON pack.pack_id=o.pack_id
                       LEFT JOIN business_subscriptions subscription
                         ON subscription.tenant_id=o.tenant_id
                       LEFT JOIN LATERAL (
                         SELECT payment_grace_days
                         FROM platform_pricing_settings setting
                         WHERE setting.plan_code=subscription.plan_code
                           AND (setting.business_type IS NULL
                                OR setting.business_type=profile.operating_profile)
                           AND setting.effective_from <= o.created_at
                         ORDER BY setting.business_type NULLS LAST,
                                  setting.effective_from DESC
                         LIMIT 1
                       ) price ON true
                       LEFT JOIN LATERAL (
                         SELECT normalized_value
                         FROM principal_identities principal_identity
                         WHERE principal_identity.account_id=o.account_id
                           AND principal_identity.verified_at IS NOT NULL
                         ORDER BY CASE principal_identity.channel
                                    WHEN 'EMAIL' THEN 0 ELSE 1 END,
                                  principal_identity.created_at
                         LIMIT 1
                       ) identity ON true
                       WHERE COALESCE(
                               CASE
                                 WHEN o.state='REFUNDED' THEN refund.updated_at
                                 WHEN o.state='CONFIRMED' THEN receipt.issued_at
                               END,
                               o.created_at
                             ) >= :start
                         AND COALESCE(
                               CASE
                                 WHEN o.state='REFUNDED' THEN refund.updated_at
                                 WHEN o.state='CONFIRMED' THEN receipt.issued_at
                               END,
                               o.created_at
                             ) < :end
                         AND ((:is_b2c AND o.tenant_id IS NULL
                                           AND o.retail_package_id IS NOT NULL)
                              OR (NOT :is_b2c AND o.tenant_id IS NOT NULL
                                                  AND o.pack_id IS NOT NULL))
                       ORDER BY o.created_at DESC, o.payment_order_id DESC"""
                ),
                {"start": start, "end": end, "is_b2c": is_b2c},
            ).mappings()

            now = datetime.now(UTC)
            items: list[dict[str, object]] = []
            for row in rows:
                item = dict(row)
                raw_state = str(item.pop("state"))
                if raw_state == "REFUNDED":
                    derived_status = "REFUNDED"
                elif is_b2c:
                    derived_status = payment_status(raw_state, now, 100_000, now)
                else:
                    derived_status = payment_status(
                        raw_state,
                        cast(datetime, item["created_at"]),
                        int(item.pop("grace_days")),
                        now,
                    )
                item.pop("grace_days", None)
                item["payment_status"] = derived_status
                item["customer_name"] = (
                    item.pop("customer_identity") if is_b2c else item.pop("organization_name")
                ) or "Unknown account"
                item["package_name"] = (
                    item.pop("retail_package_name") if is_b2c else item.pop("business_package_name")
                ) or "Unspecified"
                item.pop("organization_name", None)
                item.pop("retail_package_name", None)
                item.pop("business_package_name", None)
                if wanted_status is None or derived_status == wanted_status:
                    items.append(item)

        paid = [item for item in items if item["payment_status"] == "PAID"]
        collected_minor = sum(cast(int, item["amount_minor"]) for item in paid)
        return {
            "audience": wanted_audience,
            "date_from": date_from,
            "date_to": date_to,
            "currency": "INR",
            "summary": {
                "transactions": len(items),
                "collected_minor": collected_minor,
                "paid": len(paid),
                "pending": sum(item["payment_status"] == "PENDING" for item in items),
                "overdue": sum(item["payment_status"] == "OVERDUE" for item in items),
                "failed": sum(item["payment_status"] == "FAILED" for item in items),
                "refunded": sum(item["payment_status"] == "REFUNDED" for item in items),
                "refunded_minor": sum(
                    cast(int, item["refunded_amount_minor"] or item["amount_minor"])
                    for item in items
                    if item["payment_status"] == "REFUNDED"
                ),
                "average_payment_minor": round(collected_minor / len(paid)) if paid else 0,
                "tokens_credited": sum(cast(int, item["tokens_credited"]) for item in paid),
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
