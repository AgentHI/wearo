"""Persist email OTP challenges and hashed browser-session credentials.

Revision ID: 20261017_0013
Revises: 20261017_0012
Created: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261017_0013"
down_revision: str | None = "20261017_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {
    "email_otp_requests": {"classification": "audit", "owner_columns": []},
    "email_otp_challenges": {"classification": "audit", "owner_columns": []},
}

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("sessions", sa.Column("session_token_hash", sa.LargeBinary()))
    op.add_column("sessions", sa.Column("csrf_token_hash", sa.LargeBinary()))
    op.add_column("sessions", sa.Column("rotated_at", TIMESTAMP))
    op.create_check_constraint(
        "ck_sessions_credential_pair",
        "sessions",
        "(session_token_hash IS NULL) = (csrf_token_hash IS NULL)",
    )
    op.create_unique_constraint("uq_sessions_token_hash", "sessions", ["session_token_hash"])

    op.create_table(
        "email_otp_requests",
        sa.Column(
            "request_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("normalized_email_hash", sa.LargeBinary(), nullable=False),
        sa.Column("auth_realm", sa.String(16), nullable=False),
        sa.Column("requested_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "auth_realm IN ('SHOP', 'BUSINESS')", name="ck_email_otp_requests_realm"
        ),
    )
    op.create_index(
        "ix_email_otp_requests_throttle",
        "email_otp_requests",
        ["normalized_email_hash", "auth_realm", "requested_at"],
    )

    op.create_table(
        "email_otp_challenges",
        sa.Column("challenge_id", UUID, primary_key=True),
        sa.Column("identity_id", UUID, nullable=False),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("consumed_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_email_otp_challenges_attempts"),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["principal_identities.identity_id"],
            name="fk_email_otp_challenges_identity",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_email_otp_challenges_expiry",
        "email_otp_challenges",
        ["expires_at", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_otp_challenges_expiry", table_name="email_otp_challenges")
    op.drop_table("email_otp_challenges")
    op.drop_index("ix_email_otp_requests_throttle", table_name="email_otp_requests")
    op.drop_table("email_otp_requests")
    op.drop_constraint("uq_sessions_token_hash", "sessions", type_="unique")
    op.drop_constraint("ck_sessions_credential_pair", "sessions", type_="check")
    op.drop_column("sessions", "rotated_at")
    op.drop_column("sessions", "csrf_token_hash")
    op.drop_column("sessions", "session_token_hash")
