"""Add per-user Google Drive connections and durable image sync jobs.

Revision ID: 20261119_0088
Revises: 20261116_0087
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261119_0088"
down_revision: str | None = "20261116_0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES = {
    "user_drive_connections": {
        "classification": "private",
        "owner_columns": ["account_id"],
    },
    "drive_sync_jobs": {
        "classification": "private",
        "owner_columns": ["account_id"],
    },
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "user_drive_connections",
        sa.Column(
            "connection_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("google_subject", sa.String(255)),
        sa.Column("google_email", sa.String(320)),
        sa.Column("encrypted_refresh_token", sa.LargeBinary()),
        sa.Column("root_folder_id", sa.String(255)),
        sa.Column("tryons_folder_id", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False, server_default="DISCONNECTED"),
        sa.Column("auto_sync_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oauth_state_hash", sa.LargeBinary()),
        sa.Column("encrypted_code_verifier", sa.LargeBinary()),
        sa.Column("oauth_session_hash", sa.LargeBinary()),
        sa.Column("oauth_state_expires_at", TIMESTAMP),
        sa.Column("last_successful_sync_at", TIMESTAMP),
        sa.Column("failed_sync_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('CONNECTING', 'CONNECTED', 'RECONNECT_REQUIRED', 'DISCONNECTED')",
            name="ck_user_drive_connections_status",
        ),
        sa.CheckConstraint("failed_sync_count >= 0", name="ck_user_drive_connections_failures"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_drive_connections_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("account_id", name="uq_user_drive_connections_account"),
        sa.UniqueConstraint(
            "connection_id", "account_id", name="uq_user_drive_connections_id_account"
        ),
    )
    op.create_index(
        "uq_user_drive_connections_google_subject",
        "user_drive_connections",
        ["google_subject"],
        unique=True,
        postgresql_where=sa.text("google_subject IS NOT NULL AND status <> 'DISCONNECTED'"),
    )
    op.create_index(
        "ix_user_drive_connections_oauth_state",
        "user_drive_connections",
        ["oauth_state_hash"],
        unique=True,
        postgresql_where=sa.text("oauth_state_hash IS NOT NULL"),
    )

    op.create_table(
        "drive_sync_jobs",
        sa.Column("job_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("render_job_id", UUID, nullable=False),
        sa.Column("result_asset_id", UUID, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("lease_expires_at", TIMESTAMP),
        sa.Column("worker_id", sa.String(200)),
        sa.Column("drive_file_id", sa.String(255)),
        sa.Column("encrypted_upload_session", sa.LargeBinary()),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("last_error_message", sa.String(500)),
        sa.Column("synced_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY', 'COMPLETED', "
            "'CANCELLED', 'PERMANENT_FAILURE')",
            name="ck_drive_sync_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_drive_sync_jobs_attempts"),
        sa.ForeignKeyConstraint(
            ["connection_id", "account_id"],
            ["user_drive_connections.connection_id", "user_drive_connections.account_id"],
            name="fk_drive_sync_jobs_connection_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_drive_sync_jobs_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["render_job_id"],
            ["render_jobs.job_id"],
            name="fk_drive_sync_jobs_render",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["result_asset_id"],
            ["media_assets.asset_id"],
            name="fk_drive_sync_jobs_asset",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("render_job_id", name="uq_drive_sync_jobs_render"),
    )
    op.create_index(
        "ix_drive_sync_jobs_claim",
        "drive_sync_jobs",
        ["status", "available_at", "created_at"],
        postgresql_where=sa.text("status IN ('PENDING', 'RETRY')"),
    )
    op.create_index(
        "ix_drive_sync_jobs_account_status", "drive_sync_jobs", ["account_id", "status"]
    )
    op.create_index(
        "uq_drive_sync_jobs_drive_file",
        "drive_sync_jobs",
        ["drive_file_id"],
        unique=True,
        postgresql_where=sa.text("drive_file_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("drive_sync_jobs")
    op.drop_table("user_drive_connections")
