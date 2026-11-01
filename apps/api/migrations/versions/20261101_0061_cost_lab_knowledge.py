"""Add Cost Lab knowledge library.

Revision ID: 20261101_0061
Revises: 20261101_0060
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261101_0061"
down_revision: str | None = "20261101_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE cost_lab.knowledge_items (
      knowledge_id uuid PRIMARY KEY,
      source_type text NOT NULL CHECK (source_type IN ('PDF','TEXT')),
      title text NOT NULL,
      content_text text,
      file_path text,
      original_filename text,
      mime_type text,
      size_bytes bigint NOT NULL DEFAULT 0,
      content_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CHECK (
        (source_type = 'TEXT' AND content_text IS NOT NULL AND file_path IS NULL)
        OR (source_type = 'PDF' AND file_path IS NOT NULL)
      )
    );
    CREATE INDEX ix_cost_lab_knowledge_created_at
      ON cost_lab.knowledge_items(created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE cost_lab.knowledge_items")
