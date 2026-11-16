"""Allow names from deleted retail packages to be reused.

Revision ID: 20261115_0085
Revises: 20261115_0084
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261115_0085"
down_revision: str | None = "20261115_0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_retail_tryon_package_name", "retail_tryon_packages", type_="unique")
    op.create_index(
        "uq_active_retail_tryon_package_name",
        "retail_tryon_packages",
        [sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("active=true"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_retail_tryon_package_name", table_name="retail_tryon_packages")
    op.create_unique_constraint(
        "uq_retail_tryon_package_name", "retail_tryon_packages", ["name"]
    )
