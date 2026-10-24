"""Replace UUID-suffixed business slugs with clean unique name slugs.

Revision ID: 20261024_0030
Revises: 20261024_0029
Created: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261024_0030"
down_revision: str | None = "20261024_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.execute(
        """
        WITH prepared AS (
            SELECT t.tenant_id,
                   trim(both '-' FROM regexp_replace(
                       lower(p.display_name), '[^a-z0-9]+', '-', 'g'
                   )) AS base_slug
            FROM business_tenants t
            JOIN business_profiles p
              ON p.tenant_id = t.tenant_id AND p.account_id = t.account_id
        ), ranked AS (
            SELECT tenant_id, base_slug,
                   row_number() OVER (PARTITION BY base_slug ORDER BY tenant_id) AS position
            FROM prepared
        )
        UPDATE business_tenants t
        SET slug = CASE
            WHEN ranked.position = 1 THEN left(ranked.base_slug, 60)
            ELSE left(ranked.base_slug, 55) || '-' || (1000 + ranked.position)::text
        END,
        updated_at = now()
        FROM ranked
        WHERE ranked.tenant_id = t.tenant_id
        """
    )


def downgrade() -> None:
    # Clean slugs remain valid and cannot be restored to their prior random values.
    pass
