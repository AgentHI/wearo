from pathlib import Path

import pytest

from scripts.validate_migrations import MigrationPolicyError, validate_revision


def test_baseline_revision_satisfies_policy() -> None:
    revision = validate_revision(Path("apps/api/migrations/versions/20261017_0001_baseline.py"))
    assert revision == "20261017_0001"


def test_private_table_without_owner_is_rejected(tmp_path: Path) -> None:
    migration = tmp_path / "bad_revision.py"
    migration.write_text(
        """
from alembic import op
import sqlalchemy as sa
revision = "bad"
TABLE_POLICIES = {
    "private_asset": {"classification": "private", "owner_columns": []},
}
op.create_table(
    "private_asset",
    sa.Column("id", sa.String()),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("updated_at", sa.DateTime()),
)
""",
        encoding="utf-8",
    )

    with pytest.raises(MigrationPolicyError, match="requires an owner column"):
        validate_revision(migration)
