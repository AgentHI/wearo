"""Add short numeric public codes for business shop links.

Revision ID: 20261024_0032
Revises: 20261024_0031
Created: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0032"
down_revision: str | None = "20261024_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column("business_shop_links", sa.Column("public_code", sa.String(8)))
    op.execute(
        """
        WITH numbered AS (
            SELECT tenant_id, row_number() OVER (ORDER BY tenant_id) AS position
            FROM business_shop_links
        )
        UPDATE business_shop_links links
        SET public_code = lpad((10000000 + numbered.position)::text, 8, '0')
        FROM numbered
        WHERE numbered.tenant_id = links.tenant_id
        """
    )
    op.alter_column("business_shop_links", "public_code", nullable=False)
    op.create_unique_constraint(
        "uq_business_shop_links_public_code", "business_shop_links", ["public_code"]
    )
    op.create_check_constraint(
        "ck_business_shop_links_public_code",
        "business_shop_links",
        "public_code ~ '^[0-9]{8}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_business_shop_links_public_code", "business_shop_links", type_="check"
    )
    op.drop_constraint(
        "uq_business_shop_links_public_code", "business_shop_links", type_="unique"
    )
    op.drop_column("business_shop_links", "public_code")
