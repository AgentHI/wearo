"""Add public business contact enquiries.

Revision ID: 20261028_0049
Revises: 20261026_0048
Created: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0049"
down_revision: str | None = "20261026_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES = {
    "contact_enquiries": {"classification": "audit", "owner_columns": []},
}
UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "contact_enquiries",
        sa.Column(
            "contact_enquiry_id",
            UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("mobile", sa.String(32), nullable=False),
        sa.Column("website_url", sa.String(2048)),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="SUBMITTED"),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "purpose IN ('BRAND_TRY_ON', 'RETAIL_PARTNERSHIP', 'ENTERPRISE_DEMO', "
            "'TECHNOLOGY_PARTNERSHIP', 'PRESS', 'OTHER')",
            name="ck_contact_enquiries_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'IN_REVIEW', 'CLOSED')",
            name="ck_contact_enquiries_status",
        ),
        sa.UniqueConstraint("request_id", name="uq_contact_enquiries_request_id"),
    )
    op.create_index(
        "ix_contact_enquiries_status_created",
        "contact_enquiries",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_contact_enquiries_status_created", table_name="contact_enquiries")
    op.drop_table("contact_enquiries")
