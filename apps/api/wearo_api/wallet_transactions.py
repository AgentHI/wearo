from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope

TransactionCategory = Literal["PURCHASE", "PROMOTIONAL_CREDIT", "CONSUMPTION", "REFUND", "EXPIRY"]


class WalletTransactionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def transaction_category(entry_type: str, bucket_type: str) -> TransactionCategory:
    if entry_type == "CREDIT":
        return "PROMOTIONAL_CREDIT" if bucket_type == "PROMO" else "PURCHASE"
    categories: dict[str, TransactionCategory] = {
        "DEBIT": "CONSUMPTION",
        "RECREDIT": "REFUND",
        "EXPIRY": "EXPIRY",
    }
    try:
        return categories[entry_type]
    except KeyError:
        raise WalletTransactionError(
            "TRANSACTION_TYPE_UNAVAILABLE", "Transaction type is not reportable."
        ) from None


def transactions_csv(items: list[dict[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["transaction_id", "occurred_at", "category", "amount", "balance"])
    for item in items:
        writer.writerow(
            [
                item["transaction_id"],
                item["occurred_at"],
                item["category"],
                item["amount"],
                item["balance_after"],
            ]
        )
    return output.getvalue()


class PostgresWalletTransactions:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _account(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(connection, principal_id, tenant_id).account_id
        except TenantScopeError:
            raise WalletTransactionError(
                "TRANSACTION_HISTORY_UNAVAILABLE", "Resource unavailable."
            ) from None

    def history(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        category: TransactionCategory | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, object]:
        if date_from and date_to and date_from > date_to:
            raise WalletTransactionError("INVALID_DATE_RANGE", "Start date must precede end date.")
        with self.engine.connect() as connection:
            account_id = self._account(connection, principal_id, tenant_id)
            rows = list(
                connection.execute(
                    text(
                        """
                        SELECT * FROM (
                            SELECT e.entry_id, e.entry_type, e.amount, e.created_at,
                                   b.bucket_type, sum(e.amount) OVER (
                                       PARTITION BY e.account_id
                                       ORDER BY e.created_at, e.entry_id
                                   ) AS balance_after
                            FROM ledger_entries e
                            JOIN wallet_buckets b
                              ON b.bucket_id = e.bucket_id AND b.account_id = e.account_id
                            WHERE e.account_id = :account AND e.tenant_id = :tenant
                        ) history
                        WHERE (:from_time IS NULL OR history.created_at >= :from_time)
                          AND (:to_time IS NULL OR history.created_at < :to_time)
                        ORDER BY history.created_at DESC, history.entry_id DESC
                        """
                    ),
                    {
                        "account": account_id,
                        "tenant": tenant_id,
                        "from_time": datetime.combine(date_from, time.min) if date_from else None,
                        "to_time": (
                            datetime.combine(date_to + timedelta(days=1), time.min)
                            if date_to
                            else None
                        ),
                    },
                ).mappings()
            )
        items = [
            {
                "transaction_id": row["entry_id"],
                "occurred_at": row["created_at"],
                "category": transaction_category(row["entry_type"], row["bucket_type"]),
                "amount": row["amount"],
                "balance_after": row["balance_after"],
            }
            for row in rows
            if row["entry_type"] in {"CREDIT", "DEBIT", "RECREDIT", "EXPIRY"}
        ]
        if category:
            items = [item for item in items if item["category"] == category]
        net_change = sum(int(item["amount"]) for item in items)
        closing_balance = int(items[0]["balance_after"]) if items else 0
        return {
            "unit": "WEARO_TOKEN",
            "opening_balance": closing_balance - net_change,
            "closing_balance": closing_balance,
            "net_change": net_change,
            "items": items,
        }
