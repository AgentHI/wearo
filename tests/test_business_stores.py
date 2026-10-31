from pathlib import Path

import pytest

from apps.api.wearo_api.business_stores import BusinessStoreError, validate_store
from scripts.validate_migrations import validate_revision


def test_store_name_and_code_are_normalized() -> None:
    assert validate_store("  Indiranagar  ", " Bengaluru / Indiranagar ") == (
        "Indiranagar",
        "bengaluru-indiranagar",
    )


@pytest.mark.parametrize(("name", "code"), [("", "main"), ("Main", "---")])
def test_store_requires_name_and_code(name: str, code: str) -> None:
    with pytest.raises(BusinessStoreError):
        validate_store(name, code)


def test_store_migration_satisfies_policy_and_backfills_agents() -> None:
    path = Path("apps/api/migrations/versions/20261031_0052_business_stores.py")
    assert validate_revision(path) == "20261031_0052"
    source = path.read_text(encoding="utf-8")
    assert "'Main Store', 'main'" in source
    assert "UPDATE business_agents a SET store_id=s.store_id" in source
    assert 'op.alter_column("business_agents", "store_id", nullable=False)' in source
