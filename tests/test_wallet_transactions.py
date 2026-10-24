from datetime import UTC, datetime
from uuid import UUID

import pytest

from apps.api.wearo_api.wallet_transactions import (
    WalletTransactionError,
    transaction_category,
    transactions_csv,
)


@pytest.mark.parametrize(
    ("entry_type", "bucket_type", "expected"),
    [
        ("CREDIT", "PURCHASED", "PURCHASE"),
        ("CREDIT", "PROMO", "PROMOTIONAL_CREDIT"),
        ("DEBIT", "PURCHASED", "CONSUMPTION"),
        ("RECREDIT", "PURCHASED", "REFUND"),
        ("EXPIRY", "PROMO", "EXPIRY"),
    ],
)
def test_transaction_category_explains_ledger_activity(
    entry_type: str, bucket_type: str, expected: str
) -> None:
    assert transaction_category(entry_type, bucket_type) == expected


def test_non_reportable_ledger_activity_is_rejected() -> None:
    with pytest.raises(WalletTransactionError) as raised:
        transaction_category("HOLD", "PURCHASED")
    assert raised.value.code == "TRANSACTION_TYPE_UNAVAILABLE"


def test_csv_is_downloadable_and_reconciliation_friendly() -> None:
    result = transactions_csv(
        [
            {
                "transaction_id": UUID("00000000-0000-0000-0000-000000000001"),
                "occurred_at": datetime(2026, 10, 23, 10, 30, tzinfo=UTC),
                "category": "REFUND",
                "amount": 5,
                "balance_after": 25,
            }
        ]
    )
    assert "transaction_id,occurred_at,category,amount,balance" in result
    assert "REFUND,5,25" in result
