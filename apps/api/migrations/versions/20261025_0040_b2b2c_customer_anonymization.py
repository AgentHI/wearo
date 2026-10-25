"""Anonymize deleted B2B2C customers without losing business aggregates.

Revision ID: 20261025_0040
Revises: 20261025_0039
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261025_0040"
down_revision: str | None = "20261025_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("business_participants", sa.Column("anonymized_at", TIMESTAMP))
    op.add_column("business_sponsored_tryons", sa.Column("render_job_id", UUID))
    op.create_foreign_key(
        "fk_sponsored_tryons_render_job",
        "business_sponsored_tryons",
        "render_jobs",
        ["render_job_id"],
        ["job_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sponsored_tryons_render_job",
        "business_sponsored_tryons",
        ["render_job_id"],
    )
    op.execute(
        """
        UPDATE business_sponsored_tryons sponsored
        SET render_job_id = job.job_id
        FROM business_sponsored_sessions session, render_jobs job
        WHERE session.session_id = sponsored.session_id
          AND job.account_id = session.consumer_account_id
          AND job.tenant_id IS NULL
          AND job.idempotency_key = substring(sponsored.request_key FROM 11)
        """
    )

    op.drop_constraint(
        "fk_business_participants_consumer", "business_participants", type_="foreignkey"
    )
    op.alter_column("business_participants", "consumer_account_id", nullable=True)
    op.alter_column("business_participants", "consumer_principal_id", nullable=True)
    op.create_foreign_key(
        "fk_business_participants_consumer",
        "business_participants",
        "principals",
        ["consumer_principal_id", "consumer_account_id"],
        ["principal_id", "account_id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_sponsored_sessions_consumer", "business_sponsored_sessions", type_="foreignkey"
    )
    op.alter_column("business_sponsored_sessions", "consumer_account_id", nullable=True)
    op.alter_column("business_sponsored_sessions", "consumer_principal_id", nullable=True)
    op.create_foreign_key(
        "fk_sponsored_sessions_consumer",
        "business_sponsored_sessions",
        "principals",
        ["consumer_principal_id", "consumer_account_id"],
        ["principal_id", "account_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Anonymized rows cannot truthfully regain their deleted consumer identity.
    op.execute(
        "DELETE FROM business_participants "
        "WHERE consumer_account_id IS NULL OR consumer_principal_id IS NULL"
    )
    op.drop_constraint(
        "fk_sponsored_sessions_consumer", "business_sponsored_sessions", type_="foreignkey"
    )
    op.alter_column("business_sponsored_sessions", "consumer_account_id", nullable=False)
    op.alter_column("business_sponsored_sessions", "consumer_principal_id", nullable=False)
    op.create_foreign_key(
        "fk_sponsored_sessions_consumer",
        "business_sponsored_sessions",
        "principals",
        ["consumer_principal_id", "consumer_account_id"],
        ["principal_id", "account_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_business_participants_consumer", "business_participants", type_="foreignkey"
    )
    op.alter_column("business_participants", "consumer_account_id", nullable=False)
    op.alter_column("business_participants", "consumer_principal_id", nullable=False)
    op.create_foreign_key(
        "fk_business_participants_consumer",
        "business_participants",
        "principals",
        ["consumer_principal_id", "consumer_account_id"],
        ["principal_id", "account_id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_sponsored_tryons_render_job", table_name="business_sponsored_tryons")
    op.drop_constraint(
        "fk_sponsored_tryons_render_job", "business_sponsored_tryons", type_="foreignkey"
    )
    op.drop_column("business_sponsored_tryons", "render_job_id")
    op.drop_column("business_participants", "anonymized_at")
