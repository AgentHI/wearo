"""Add the separate administrator credential and session realm.

Revision ID: 20261017_0008
Revises: 20261017_0007
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0008"
down_revision: str | None = "20261017_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "admin_identities": {"classification": "audit", "owner_columns": []},
    "admin_mfa_challenges": {"classification": "audit", "owner_columns": []},
    "admin_sessions": {"classification": "audit", "owner_columns": []},
    "admin_recovery_codes": {"classification": "audit", "owner_columns": []},
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "admin_identities",
        sa.Column("admin_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.LargeBinary(), nullable=False),
        sa.Column("mfa_secret_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("failed_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("locked_until", TIMESTAMP),
        sa.Column("last_authenticated_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "username = lower(username)", name="ck_admin_identities_normalized_username"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')", name="ck_admin_identities_status"
        ),
        sa.CheckConstraint("failed_attempts >= 0", name="ck_admin_identities_failed_attempts"),
        sa.UniqueConstraint("username", name="uq_admin_identities_username"),
    )

    op.create_table(
        "admin_mfa_challenges",
        sa.Column(
            "challenge_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("admin_id", UUID, nullable=False),
        sa.Column("challenge_token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("consumed_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("attempts >= 0", name="ck_admin_mfa_challenges_attempts"),
        sa.CheckConstraint("expires_at > created_at", name="ck_admin_mfa_challenges_expiry"),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admin_identities.admin_id"], name="fk_admin_mfa_challenges_admin"
        ),
        sa.UniqueConstraint("challenge_token_hash", name="uq_admin_mfa_challenges_token_hash"),
    )
    op.create_index(
        "ix_admin_mfa_challenges_admin_active",
        "admin_mfa_challenges",
        ["admin_id", "expires_at"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )

    op.create_table(
        "admin_sessions",
        sa.Column(
            "admin_session_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("admin_id", UUID, nullable=False),
        sa.Column("session_token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("csrf_token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("auth_realm", sa.String(16), nullable=False, server_default="ADMIN"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("revoked_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("auth_realm = 'ADMIN'", name="ck_admin_sessions_realm"),
        sa.CheckConstraint("expires_at > created_at", name="ck_admin_sessions_expiry"),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admin_identities.admin_id"], name="fk_admin_sessions_admin"
        ),
        sa.UniqueConstraint("session_token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index(
        "ix_admin_sessions_admin_active",
        "admin_sessions",
        ["admin_id", "expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "admin_recovery_codes",
        sa.Column(
            "recovery_code_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("admin_id", UUID, nullable=False),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("used_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admin_identities.admin_id"], name="fk_admin_recovery_codes_admin"
        ),
        sa.UniqueConstraint("code_hash", name="uq_admin_recovery_codes_hash"),
    )


def downgrade() -> None:
    op.drop_table("admin_recovery_codes")
    op.drop_index("ix_admin_sessions_admin_active", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index("ix_admin_mfa_challenges_admin_active", table_name="admin_mfa_challenges")
    op.drop_table("admin_mfa_challenges")
    op.drop_table("admin_identities")
