"""Add retail try-on package catalogue.

Revision ID: 20261115_0084
Revises: 20261115_0083
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261115_0084"
down_revision: str | None = "20261115_0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retail_tryon_packages",
        sa.Column(
            "retail_package_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("minimum_amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_retail_tryon_package_name"),
        sa.CheckConstraint(
            "minimum_amount_minor > 0 AND minimum_amount_minor % 20 = 0",
            name="ck_retail_tryon_package_amount",
        ),
        sa.CheckConstraint("currency = 'INR'", name="ck_retail_tryon_package_currency"),
        sa.UniqueConstraint("name", name="uq_retail_tryon_package_name"),
    )


def downgrade() -> None:
    op.drop_table("retail_tryon_packages")
