from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from .email_otp import normalize_destination, normalize_email
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
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

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
