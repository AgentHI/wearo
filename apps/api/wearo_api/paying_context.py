from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

PayerType = Literal["CONSUMER", "BUSINESS"]


class PayingContextError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PayingContext:
    payer_type: PayerType
    account_id: UUID
    tenant_id: UUID | None


def paying_context(account_kind: str, account_id: UUID, tenant_id: UUID | None) -> PayingContext:
    if account_kind == "CONSUMER" and tenant_id is None:
        return PayingContext("CONSUMER", account_id, None)
    if account_kind == "TENANT" and tenant_id is not None:
        return PayingContext("BUSINESS", account_id, tenant_id)
    raise PayingContextError(
        "INVALID_PAYING_CONTEXT", "Exactly one valid consumer or business payer is required."
    )
