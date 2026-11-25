"""Snapshot ordered production model routes on render quotes.

Revision ID: 20261125_0099
Revises: 20261122_0098
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261125_0099"
down_revision: str | None = "20261122_0098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE render_quotes
      ADD COLUMN route_candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
      ADD CONSTRAINT ck_render_quotes_route_candidates CHECK (
        jsonb_typeof(route_candidates) = 'array'
      );

    UPDATE render_quotes
    SET route_candidates = jsonb_build_array(jsonb_build_object(
      'provider', provider,
      'model', model_version,
      'region', provider_region,
      'capability', 'APPAREL',
      'enabled', true,
      'priority', 1,
      'release_id', NULL
    ))
    WHERE provider IS NOT NULL
      AND model_version IS NOT NULL
      AND provider_region IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE render_quotes
      DROP CONSTRAINT ck_render_quotes_route_candidates,
      DROP COLUMN route_candidates;
    """)
