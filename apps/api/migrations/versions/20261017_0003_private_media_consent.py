"""Add private media, consent evidence, lifecycle, and reports.

Revision ID: 20261017_0003
Revises: 20261017_0002
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0003"
down_revision: str | None = "20261017_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "media_assets": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "consent_records": {
        "classification": "audit",
        "owner_columns": ["account_id", "tenant_id"],
    },
    "media_reports": {
        "classification": "private",
        "owner_columns": ["account_id", "tenant_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("asset_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("retention_state", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("delete_after", TIMESTAMP),
        sa.Column("deletion_state", sa.String(24), nullable=False, server_default="RETAINED"),
        sa.Column("deleted_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "purpose IN ('PERSON_SOURCE', 'PRODUCT_SOURCE', 'RENDER_RESULT')",
            name="ck_media_assets_purpose",
        ),
        sa.CheckConstraint(
            "validation_state IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_media_assets_validation_state",
        ),
        sa.CheckConstraint(
            "retention_state IN ('ACTIVE', 'EXPIRING', 'LEGAL_HOLD')",
            name="ck_media_assets_retention_state",
        ),
        sa.CheckConstraint(
            "deletion_state IN ('RETAINED', 'REQUESTED', 'QUEUED', 'DELETED')",
            name="ck_media_assets_deletion_state",
        ),
        sa.CheckConstraint(
            "(deletion_state = 'DELETED' AND deleted_at IS NOT NULL) OR "
            "(deletion_state <> 'DELETED' AND deleted_at IS NULL)",
            name="ck_media_assets_deleted_at",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_media_assets_account"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_media_assets_tenant_account",
        ),
        sa.UniqueConstraint("account_id", "asset_id", name="uq_media_assets_account_asset"),
        sa.UniqueConstraint("object_key", name="uq_media_assets_object_key"),
    )
    op.create_index(
        "ix_media_assets_owner_lifecycle",
        "media_assets",
        ["account_id", "deletion_state", "delete_after"],
    )

    op.create_table(
        "consent_records",
        sa.Column(
            "consent_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("asset_id", UUID),
        sa.Column("actor_principal_id", UUID, nullable=False),
        sa.Column("consent_version", sa.String(40), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("permission_asserted", sa.Boolean(), nullable=False),
        sa.Column("accepted_at", TIMESTAMP, nullable=False),
        sa.Column("withdrawn_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("permission_asserted", name="ck_consent_records_affirmative"),
        sa.CheckConstraint(
            "purpose IN ('TRY_ON', 'STORE_TRY_ON', 'RESULT_SAVE')",
            name="ck_consent_records_purpose",
        ),
        sa.CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= accepted_at",
            name="ck_consent_records_withdrawal_time",
        ),
        sa.ForeignKeyConstraint(
            ["actor_principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_consent_records_actor_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_consent_records_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_consent_records_asset_account",
        ),
    )
    op.create_index(
        "ix_consent_records_owner_purpose",
        "consent_records",
        ["account_id", "purpose", "accepted_at"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_consent_record_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'consent records are immutable; append a new evidence record';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_consent_records_immutable
        BEFORE UPDATE OR DELETE ON consent_records
        FOR EACH ROW EXECUTE FUNCTION reject_consent_record_mutation()
        """
    )

    op.create_table(
        "media_reports",
        sa.Column("report_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID),
        sa.Column("asset_id", UUID, nullable=False),
        sa.Column("reported_by_principal_id", UUID, nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="SUBMITTED"),
        sa.Column("resolved_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "reason IN ('REMOVE', 'PRIVACY', 'QUALITY', 'SAFETY', 'OTHER')",
            name="ck_media_reports_reason",
        ),
        sa.CheckConstraint(
            "state IN ('SUBMITTED', 'IN_REVIEW', 'RESOLVED', 'REJECTED')",
            name="ck_media_reports_state",
        ),
        sa.CheckConstraint(
            "(state IN ('RESOLVED', 'REJECTED') AND resolved_at IS NOT NULL) OR "
            "(state NOT IN ('RESOLVED', 'REJECTED') AND resolved_at IS NULL)",
            name="ck_media_reports_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["reported_by_principal_id", "account_id"],
            ["principals.principal_id", "principals.account_id"],
            name="fk_media_reports_actor_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["business_tenants.tenant_id", "business_tenants.account_id"],
            name="fk_media_reports_tenant_account",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "asset_id"],
            ["media_assets.account_id", "media_assets.asset_id"],
            name="fk_media_reports_asset_account",
        ),
    )
    op.create_index(
        "ix_media_reports_owner_state", "media_reports", ["account_id", "state", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_media_reports_owner_state", table_name="media_reports")
    op.drop_table("media_reports")
    op.execute("DROP TRIGGER trg_consent_records_immutable ON consent_records")
    op.execute("DROP FUNCTION reject_consent_record_mutation()")
    op.drop_index("ix_consent_records_owner_purpose", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_index("ix_media_assets_owner_lifecycle", table_name="media_assets")
    op.drop_table("media_assets")
