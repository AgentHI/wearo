from pathlib import Path

import pytest

from apps.api.wearo_api.business_agents import BusinessAgentError, validate_agent


def test_agent_name_and_mobile_are_normalized() -> None:
    assert validate_agent("  Priya Shah  ", "+91 (98765) 43210") == (
        "Priya Shah",
        "+919876543210",
    )


@pytest.mark.parametrize(("name", "mobile"), [("", "+919876543210"), ("Priya", "98765")])
def test_agent_requires_name_and_international_mobile(name: str, mobile: str) -> None:
    with pytest.raises(BusinessAgentError):
        validate_agent(name, mobile)


def test_new_agent_conflict_query_types_nullable_principal_as_uuid() -> None:
    source = Path("apps/api/wearo_api/business_agents.py").read_text()
    assert "CAST(:agent_principal AS uuid) IS NULL" in source
