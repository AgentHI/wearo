from uuid import uuid4

import pytest

from apps.api.wearo_api.paying_context import PayingContextError, paying_context


def test_consumer_action_uses_account_without_tenant() -> None:
    account_id = uuid4()
    context = paying_context("CONSUMER", account_id, None)
    assert context.payer_type == "CONSUMER"
    assert context.account_id == account_id


def test_business_action_uses_explicit_tenant() -> None:
    context = paying_context("TENANT", uuid4(), uuid4())
    assert context.payer_type == "BUSINESS"
    assert context.tenant_id is not None


@pytest.mark.parametrize(
    ("kind", "tenant"), [("CONSUMER", uuid4()), ("TENANT", None), ("UNKNOWN", None)]
)
def test_ambiguous_or_mismatched_payer_is_rejected(kind: str, tenant: object) -> None:
    with pytest.raises(PayingContextError):
        paying_context(kind, uuid4(), tenant)  # type: ignore[arg-type]
