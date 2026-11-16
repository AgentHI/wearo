"""Add GST to retail try-on packages.

Revision ID: 20261115_0086
Revises: 20261115_0085
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261115_0086"
down_revision: str | None = "20261115_0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retail_tryon_packages",
        sa.Column("gst_basis_points", sa.Integer(), nullable=False, server_default="1800"),
    )
    op.create_check_constraint(
        "ck_retail_tryon_package_gst",
        "retail_tryon_packages",
        "gst_basis_points BETWEEN 0 AND 10000",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_retail_tryon_package_gst", "retail_tryon_packages", type_="check"
    )
    op.drop_column("retail_tryon_packages", "gst_basis_points")
