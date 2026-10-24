from __future__ import annotations

import csv
import io
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope


class BusinessReportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PostgresBusinessReports:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise BusinessReportError("REPORT_UNAVAILABLE", "Resource unavailable.") from None

    def reconciliation(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            topups = tuple(
                dict(row)
                for row in connection.execute(
                    text("""
                SELECT o.payment_order_id, o.state, o.amount_minor, o.currency,
                       o.purchased_tokens, o.promo_tokens, o.created_at,
                       i.invoice_id, i.invoice_number, i.status AS invoice_status,
                       i.tax_minor, i.document_url
                FROM payment_orders o LEFT JOIN invoices i
                  ON i.payment_order_id=o.payment_order_id
                WHERE o.account_id=:account AND o.tenant_id=:tenant
                ORDER BY o.created_at DESC"""),
                    {"account": account_id, "tenant": tenant_id},
                ).mappings()
            )
            usage = tuple(
                dict(row)
                for row in connection.execute(
                    text("""
                SELECT e.performed_by_principal_id AS staff_principal_id,
                       COALESCE(i.normalized_value, 'SYSTEM') AS staff_identity,
                       count(*) AS transaction_count, COALESCE(-sum(e.amount), 0) AS tokens_used
                FROM ledger_entries e
                LEFT JOIN principal_identities i
                  ON i.principal_id=e.performed_by_principal_id AND i.channel='EMAIL'
                WHERE e.account_id=:account AND e.tenant_id=:tenant
                  AND e.entry_type='DEBIT' AND e.amount < 0
                GROUP BY e.performed_by_principal_id, i.normalized_value
                ORDER BY tokens_used DESC"""),
                    {"account": account_id, "tenant": tenant_id},
                ).mappings()
            )
            outlet: str = connection.execute(
                text(
                    """SELECT slug FROM business_tenants
                    WHERE tenant_id=:tenant AND account_id=:account"""
                ),
                {"tenant": tenant_id, "account": account_id},
            ).scalar_one()
        return {
            "unit": "WEARO_TOKEN",
            "outlet": outlet,
            "topups": topups,
            "usage_by_staff": usage,
            "totals": {
                "confirmed_topup_cost_minor": sum(
                    int(item["amount_minor"]) for item in topups if item["state"] == "CONFIRMED"
                ),
                "tokens_purchased": sum(
                    int(item["purchased_tokens"] or 0) + int(item["promo_tokens"] or 0)
                    for item in topups
                    if item["state"] == "CONFIRMED"
                ),
                "tokens_used": sum(int(item["tokens_used"]) for item in usage),
            },
        }


def reconciliation_csv(report: dict[str, object]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "record_type",
            "reference",
            "status",
            "amount_minor",
            "currency",
            "tokens",
            "invoice_number",
            "invoice_url",
        ]
    )
    topups = cast(tuple[dict[str, Any], ...], report["topups"])
    usage = cast(tuple[dict[str, Any], ...], report["usage_by_staff"])
    for item in topups:
        writer.writerow(
            [
                "TOPUP",
                item["payment_order_id"],
                item["state"],
                item["amount_minor"],
                item["currency"],
                int(item["purchased_tokens"] or 0) + int(item["promo_tokens"] or 0),
                item["invoice_number"] or "",
                item["document_url"] or "",
            ]
        )
    for item in usage:
        writer.writerow(
            ["USAGE", item["staff_identity"], "RECORDED", "", "", item["tokens_used"], "", ""]
        )
    return output.getvalue()
