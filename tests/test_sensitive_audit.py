import pytest

from apps.api.wearo_api.sensitive_audit import SensitiveAuditError, validate_audit_reason


def test_audit_reason_is_normalized() -> None:
    assert validate_audit_reason("  price correction  ") == "price correction"


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_sensitive_actions_require_a_bounded_reason(reason: str) -> None:
    with pytest.raises(SensitiveAuditError) as raised:
        validate_audit_reason(reason)
    assert raised.value.code == "AUDIT_REASON_REQUIRED"
