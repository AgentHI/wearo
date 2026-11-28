from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from .email_otp import VerificationEmailDeliveryProvider, normalize_destination, normalize_email
from .tenant_scope import TenantScopeError, require_tenant_scope

MembershipRole = Literal["OWNER", "ASSOCIATE"]


class BusinessMembershipError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_membership_change(
    *, current_role: MembershipRole, new_role: MembershipRole | None, active_owner_count: int
) -> None:
    removes_owner = current_role == "OWNER" and new_role != "OWNER"
    if removes_owner and active_owner_count <= 1:
        raise BusinessMembershipError(
            "LAST_OWNER_REQUIRED", "The workspace must retain at least one active owner."
        )


class PostgresBusinessMembership:
    def __init__(
        self,
        engine: Engine,
        *,
        email_provider: VerificationEmailDeliveryProvider | None = None,
        otp_pepper: bytes = b"",
        fixed_test_code: str | None = None,
    ) -> None:
        self.engine = engine
        self.email_provider = email_provider
        self.otp_pepper = otp_pepper
        self.fixed_test_code = fixed_test_code

    def _owner_email_code_hash(self, challenge_id: UUID, purpose: bytes, code: str) -> bytes:
        return hmac.new(
            self.otp_pepper,
            b"owner-email-change\0" + challenge_id.bytes + b"\0" + purpose + b"\0" + code.encode(),
            hashlib.sha256,
        ).digest()

    def request_owner_email_change(
        self, actor_id: UUID, tenant_id: UUID, *, new_email: str
    ) -> dict[str, object]:
        normalized_new_email = normalize_email(new_email)
        if not normalized_new_email:
            raise BusinessMembershipError("INVALID_EMAIL", "Enter a valid new admin email.")
        if self.email_provider is None or len(self.otp_pepper) < 32:
            raise BusinessMembershipError(
                "CONTACT_VERIFICATION_UNAVAILABLE", "Email verification is unavailable."
            )

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=10)
        challenge_id = uuid4()
        current_code = self.fixed_test_code or f"{secrets.randbelow(1_000_000):06d}"
        new_code = self.fixed_test_code or f"{secrets.randbelow(1_000_000):06d}"
        with self.engine.begin() as connection:
            account_id = self._require_owner(connection, actor_id, tenant_id)
            current_email = connection.execute(
                text(
                    """SELECT normalized_value FROM principal_identities
                    WHERE principal_id = :principal AND account_id = :account
                      AND channel = 'EMAIL' FOR UPDATE"""
                ),
                {"principal": actor_id, "account": account_id},
            ).scalar_one_or_none()
            if not current_email:
                raise BusinessMembershipError(
                    "OWNER_EMAIL_UNAVAILABLE", "The current admin email is unavailable."
                )
            if normalized_new_email == current_email:
                raise BusinessMembershipError(
                    "EMAIL_UNCHANGED", "Enter an email different from the current admin email."
                )
            email_in_use = connection.execute(
                text(
                    """SELECT 1 FROM principal_identities
                    WHERE channel = 'EMAIL' AND normalized_value = :email"""
                ),
                {"email": normalized_new_email},
            ).scalar_one_or_none()
            if email_in_use:
                raise BusinessMembershipError(
                    "CONTACT_ALREADY_IN_USE", "That email is already in use."
                )
            recent_requests = int(
                connection.execute(
                    text(
                        """SELECT count(*) FROM owner_email_change_challenges
                        WHERE principal_id = :principal AND created_at >= :since"""
                    ),
                    {"principal": actor_id, "since": now - timedelta(hours=1)},
                ).scalar_one()
            )
            if recent_requests >= 5:
                raise BusinessMembershipError(
                    "EMAIL_CHANGE_RATE_LIMITED", "Try changing the admin email again later."
                )
            connection.execute(
                text(
                    """UPDATE owner_email_change_challenges
                    SET consumed_at = :now, updated_at = :now
                    WHERE principal_id = :principal AND consumed_at IS NULL"""
                ),
                {"principal": actor_id, "now": now},
            )
            connection.execute(
                text(
                    """INSERT INTO owner_email_change_challenges
                    (challenge_id, account_id, tenant_id, principal_id, current_email,
                     new_email, current_code_hash, new_code_hash, expires_at,
                     created_at, updated_at)
                    VALUES
                    (:challenge, :account, :tenant, :principal, :current_email,
                     :new_email, :current_hash, :new_hash, :expires_at, :now, :now)"""
                ),
                {
                    "challenge": challenge_id,
                    "account": account_id,
                    "tenant": tenant_id,
                    "principal": actor_id,
                    "current_email": current_email,
                    "new_email": normalized_new_email,
                    "current_hash": self._owner_email_code_hash(
                        challenge_id, b"current", current_code
                    ),
                    "new_hash": self._owner_email_code_hash(challenge_id, b"new", new_code),
                    "expires_at": expires_at,
                    "now": now,
                },
            )

        if self.fixed_test_code is None:
            self.email_provider.send_verification_code(
                to_email=current_email,
                code=current_code,
                expires_at=expires_at,
                purpose="the current admin email",
            )
            self.email_provider.send_verification_code(
                to_email=normalized_new_email,
                code=new_code,
                expires_at=expires_at,
                purpose="the new admin email",
            )
            message = "Verification codes were sent to both email addresses."
        else:
            message = f"Test verification codes sent. Use {self.fixed_test_code} for both emails."
        return {
            "challenge_id": challenge_id,
            "expires_at": expires_at,
            "current_email": current_email,
            "new_email": normalized_new_email,
            "message": message,
        }

    def confirm_owner_email_change(
        self,
        actor_id: UUID,
        tenant_id: UUID,
        *,
        challenge_id: UUID,
        current_email_otp: str,
        new_email_otp: str,
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        invalid_code = False
        changed_email = ""
        try:
            with self.engine.begin() as connection:
                account_id = self._require_owner(connection, actor_id, tenant_id)
                challenge = (
                    connection.execute(
                        text(
                            """SELECT * FROM owner_email_change_challenges
                            WHERE challenge_id = :challenge FOR UPDATE"""
                        ),
                        {"challenge": challenge_id},
                    )
                    .mappings()
                    .one_or_none()
                )
                challenge_row: dict[str, Any] = dict(challenge) if challenge is not None else {}
                valid_state = (
                    bool(challenge_row)
                    and challenge_row["account_id"] == account_id
                    and challenge_row["tenant_id"] == tenant_id
                    and challenge_row["principal_id"] == actor_id
                    and challenge_row["consumed_at"] is None
                    and challenge_row["expires_at"] > now
                    and challenge_row["attempts"] < 5
                )
                codes_match = bool(
                    valid_state
                    and hmac.compare_digest(
                        challenge_row["current_code_hash"],
                        self._owner_email_code_hash(challenge_id, b"current", current_email_otp),
                    )
                    and hmac.compare_digest(
                        challenge_row["new_code_hash"],
                        self._owner_email_code_hash(challenge_id, b"new", new_email_otp),
                    )
                )
                if not codes_match:
                    belongs_to_actor = bool(
                        challenge_row
                        and challenge_row["account_id"] == account_id
                        and challenge_row["tenant_id"] == tenant_id
                        and challenge_row["principal_id"] == actor_id
                    )
                    if belongs_to_actor and challenge_row["attempts"] < 5:
                        connection.execute(
                            text(
                                """UPDATE owner_email_change_challenges
                                SET attempts = LEAST(attempts + 1, 5), updated_at = :now
                                WHERE challenge_id = :challenge"""
                            ),
                            {"challenge": challenge_id, "now": now},
                        )
                    invalid_code = True
                else:
                    current_email = connection.execute(
                        text(
                            """SELECT normalized_value FROM principal_identities
                            WHERE principal_id = :principal AND account_id = :account
                              AND channel = 'EMAIL' FOR UPDATE"""
                        ),
                        {"principal": actor_id, "account": account_id},
                    ).scalar_one_or_none()
                    if current_email != challenge_row["current_email"]:
                        raise BusinessMembershipError(
                            "EMAIL_CHANGE_STALE", "The admin email changed. Start again."
                        )
                    changed_email = challenge_row["new_email"]
                    connection.execute(
                        text(
                            """UPDATE principal_identities
                            SET normalized_value = :email, verified_at = :now, updated_at = :now
                            WHERE principal_id = :principal AND account_id = :account
                              AND channel = 'EMAIL'"""
                        ),
                        {
                            "email": changed_email,
                            "now": now,
                            "principal": actor_id,
                            "account": account_id,
                        },
                    )
                    connection.execute(
                        text(
                            """UPDATE owner_email_change_challenges
                            SET consumed_at = :now, updated_at = :now
                            WHERE challenge_id = :challenge"""
                        ),
                        {"challenge": challenge_id, "now": now},
                    )
                    connection.execute(
                        text(
                            """UPDATE sessions
                            SET revoked_at = COALESCE(revoked_at, :now), updated_at = :now
                            WHERE principal_id = :principal AND account_id = :account"""
                        ),
                        {"principal": actor_id, "account": account_id, "now": now},
                    )
                    connection.execute(
                        text(
                            """INSERT INTO audit_events
                            (audit_event_id, account_id, tenant_id, actor_type, actor_id, action,
                             target_type, target_id, reason, before_summary, after_summary,
                             occurred_at)
                            VALUES (:event, :account, :tenant, 'PRINCIPAL', :actor,
                                    'OWNER_EMAIL_CHANGED', 'PRINCIPAL', :actor, :reason,
                                    CAST(:before AS jsonb), CAST(:after AS jsonb), :now)"""
                        ),
                        {
                            "event": uuid4(),
                            "account": account_id,
                            "tenant": tenant_id,
                            "actor": actor_id,
                            "reason": "Dual email OTP verification completed",
                            "before": json.dumps({"email": current_email}),
                            "after": json.dumps({"email": changed_email}),
                            "now": now,
                        },
                    )
        except IntegrityError as error:
            raise BusinessMembershipError(
                "CONTACT_ALREADY_IN_USE", "That email is already in use."
            ) from error

        if invalid_code:
            raise BusinessMembershipError(
                "INVALID_CONTACT_OTP", "Enter the valid codes sent to both email addresses."
            )
        return {"email": changed_email, "signed_out": True}

    @staticmethod
    def _require_owner(connection: Connection, actor_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, actor_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise BusinessMembershipError(
                "MEMBERSHIP_UNAVAILABLE", "Resource unavailable."
            ) from None

    def list(self, actor_id: UUID, tenant_id: UUID) -> tuple[dict[str, object], ...]:
        with self.engine.connect() as connection:
            account_id = self._require_owner(connection, actor_id, tenant_id)
            rows = connection.execute(
                text(
                    """
                    SELECT m.membership_id, m.principal_id, m.role, m.revoked_at,
                           i.normalized_value AS email, m.created_at, m.updated_at
                    FROM tenant_memberships m
                    LEFT JOIN principal_identities i
                      ON i.principal_id = m.principal_id AND i.account_id = m.account_id
                     AND i.channel = 'EMAIL'
                    WHERE m.tenant_id = :tenant AND m.account_id = :account
                    ORDER BY m.revoked_at NULLS FIRST, m.created_at, m.membership_id
                    """
                ),
                {"tenant": tenant_id, "account": account_id},
            ).mappings()
            return tuple(dict(row) for row in rows)

    def owner_contacts(self, actor_id: UUID, tenant_id: UUID) -> dict[str, str]:
        with self.engine.connect() as connection:
            self._require_owner(connection, actor_id, tenant_id)
            rows = connection.execute(
                text(
                    """SELECT channel, normalized_value FROM principal_identities
                    WHERE principal_id = :principal AND channel IN ('EMAIL', 'PHONE')"""
                ),
                {"principal": actor_id},
            ).mappings()
            contacts = {row["channel"]: row["normalized_value"] for row in rows}
        return {"email": contacts.get("EMAIL", ""), "mobile": contacts.get("PHONE", "")}

    def update_owner_contacts(
        self, actor_id: UUID, tenant_id: UUID, *, email: str, mobile: str, reason: str
    ) -> dict[str, str]:
        normalized_email = normalize_email(email)
        normalized_mobile = normalize_destination(mobile)
        explanation = reason.strip()
        if not normalized_email:
            raise BusinessMembershipError("INVALID_EMAIL", "Enter a valid work email address.")
        if not normalized_mobile or "@" in normalized_mobile:
            raise BusinessMembershipError(
                "INVALID_MOBILE", "Enter a mobile number with its international country code."
            )
        if not explanation or len(explanation) > 500:
            raise BusinessMembershipError("CHANGE_REASON_REQUIRED", "A change reason is required.")
        current_time = datetime.now(UTC)
        try:
            with self.engine.begin() as connection:
                account_id = self._require_owner(connection, actor_id, tenant_id)
                before = self.owner_contacts(actor_id, tenant_id)
                for channel, value in (("EMAIL", normalized_email), ("PHONE", normalized_mobile)):
                    connection.execute(
                        text(
                            """INSERT INTO principal_identities
                            (identity_id, account_id, principal_id, channel, normalized_value,
                             verified_at, created_at, updated_at)
                            VALUES (:identity, :account, :principal, :channel, :value,
                                    :now, :now, :now)
                            ON CONFLICT (principal_id, channel) DO UPDATE
                            SET normalized_value = EXCLUDED.normalized_value,
                                verified_at = EXCLUDED.verified_at,
                                updated_at = EXCLUDED.updated_at"""
                        ),
                        {
                            "identity": uuid4(),
                            "account": account_id,
                            "principal": actor_id,
                            "channel": channel,
                            "value": value,
                            "now": current_time,
                        },
                    )
                after = {"email": normalized_email, "mobile": normalized_mobile}
                connection.execute(
                    text(
                        """INSERT INTO audit_events
                        (audit_event_id, account_id, tenant_id, actor_type, actor_id, action,
                         target_type, target_id, reason, before_summary, after_summary, occurred_at)
                        VALUES (:event, :account, :tenant, 'PRINCIPAL', :actor,
                                'OWNER_CONTACTS_UPDATED', 'PRINCIPAL', :actor, :reason,
                                CAST(:before AS jsonb), CAST(:after AS jsonb), :now)"""
                    ),
                    {
                        "event": uuid4(),
                        "account": account_id,
                        "tenant": tenant_id,
                        "actor": actor_id,
                        "reason": explanation,
                        "before": json.dumps(before),
                        "after": json.dumps(after),
                        "now": current_time,
                    },
                )
        except IntegrityError as error:
            raise BusinessMembershipError(
                "CONTACT_ALREADY_IN_USE", "That email or mobile is already in use."
            ) from error
        return after

    def change(
        self,
        actor_id: UUID,
        tenant_id: UUID,
        membership_id: UUID,
        *,
        new_role: MembershipRole | None,
        reason: str,
    ) -> dict[str, object]:
        explanation = reason.strip()
        if not explanation or len(explanation) > 500:
            raise BusinessMembershipError("CHANGE_REASON_REQUIRED", "A change reason is required.")
        current_time = datetime.now(UTC)
        with self.engine.begin() as connection:
            account_id = self._require_owner(connection, actor_id, tenant_id)
            membership = (
                connection.execute(
                    text(
                        """
                    SELECT membership_id, principal_id, role, revoked_at
                    FROM tenant_memberships
                    WHERE membership_id = :membership AND tenant_id = :tenant
                      AND account_id = :account FOR UPDATE
                    """
                    ),
                    {"membership": membership_id, "tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if membership is None or membership["revoked_at"] is not None:
                raise BusinessMembershipError("MEMBERSHIP_UNAVAILABLE", "Resource unavailable.")
            owner_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*) FROM tenant_memberships
                        WHERE tenant_id = :tenant AND account_id = :account
                          AND role = 'OWNER' AND revoked_at IS NULL
                        """
                    ),
                    {"tenant": tenant_id, "account": account_id},
                ).scalar_one()
            )
            validate_membership_change(
                current_role=membership["role"],
                new_role=new_role,
                active_owner_count=owner_count,
            )
            if new_role is None:
                connection.execute(
                    text(
                        """
                        UPDATE tenant_memberships SET revoked_at = :now, updated_at = :now
                        WHERE membership_id = :membership
                        """
                    ),
                    {"now": current_time, "membership": membership_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE sessions SET revoked_at = COALESCE(revoked_at, :now),
                            updated_at = :now
                        WHERE principal_id = :principal AND account_id = :account
                        """
                    ),
                    {
                        "now": current_time,
                        "principal": membership["principal_id"],
                        "account": account_id,
                    },
                )
                action = "TENANT_MEMBERSHIP_REVOKED"
            else:
                connection.execute(
                    text(
                        """
                        UPDATE tenant_memberships SET role = :role, updated_at = :now
                        WHERE membership_id = :membership
                        """
                    ),
                    {"role": new_role, "now": current_time, "membership": membership_id},
                )
                action = "TENANT_MEMBERSHIP_ROLE_CHANGED"
            before = dict(membership)
            after = {**before, "role": new_role or before["role"]}
            if new_role is None:
                after["revoked_at"] = current_time
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (audit_event_id, account_id, tenant_id, actor_type, actor_id,
                         action, target_type, target_id, reason, before_summary,
                         after_summary, occurred_at)
                    VALUES
                        (:event, :account, :tenant, 'PRINCIPAL', :actor, :action,
                         'TENANT_MEMBERSHIP', :membership, :reason,
                         CAST(:before AS jsonb), CAST(:after AS jsonb), :now)
                    """
                ),
                {
                    "event": uuid4(),
                    "account": account_id,
                    "tenant": tenant_id,
                    "actor": actor_id,
                    "action": action,
                    "membership": membership_id,
                    "reason": explanation,
                    "before": json.dumps(before, default=str),
                    "after": json.dumps(after, default=str),
                    "now": current_time,
                },
            )
        return after
