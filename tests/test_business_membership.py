import pytest

from apps.api.wearo_api.business_membership import (
    BusinessMembershipError,
    validate_membership_change,
)


def test_last_owner_cannot_be_revoked_or_demoted() -> None:
    for new_role in (None, "ASSOCIATE"):
        with pytest.raises(BusinessMembershipError) as error:
            validate_membership_change(
                current_role="OWNER", new_role=new_role, active_owner_count=1
            )
        assert error.value.code == "LAST_OWNER_REQUIRED"


def test_owner_can_be_changed_when_another_owner_remains() -> None:
    validate_membership_change(current_role="OWNER", new_role="ASSOCIATE", active_owner_count=2)


def test_associate_can_be_revoked_without_owner_count_change() -> None:
    validate_membership_change(current_role="ASSOCIATE", new_role=None, active_owner_count=1)
