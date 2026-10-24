from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .browser_sessions import BrowserSession
from .email_otp import AuthRealm, EmailOtpChallenge, OtpIdentity


def _identity_from_row(row: object) -> OtpIdentity:
    values = row._mapping  # type: ignore[attr-defined]
    return OtpIdentity(
        identity_id=values["identity_id"],
        principal_id=values["principal_id"],
        account_id=values["account_id"],
        normalized_email=values["normalized_value"],
        realm=values["realm"],
        status=values["effective_status"],
    )


IDENTITY_SELECT = """
    SELECT
        identity.identity_id,
        identity.principal_id,
        identity.account_id,
        identity.normalized_value,
        CASE principal.principal_type
            WHEN 'CONSUMER' THEN 'SHOP'
            ELSE 'BUSINESS'
        END AS realm,
        CASE
            WHEN principal.status = 'ACTIVE' AND account.status = 'ACTIVE' THEN 'ACTIVE'
            ELSE 'DISABLED'
        END AS effective_status
    FROM principal_identities AS identity
    JOIN principals AS principal
      ON principal.principal_id = identity.principal_id
     AND principal.account_id = identity.account_id
    JOIN accounts AS account ON account.account_id = identity.account_id
"""


class PostgresEmailOtpStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def resolve_identity(self, normalized_email: str, realm: AuthRealm) -> OtpIdentity | None:
        channel = "EMAIL" if "@" in normalized_email else "PHONE"
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    IDENTITY_SELECT
                    + """
                      WHERE identity.channel = :channel
                        AND identity.normalized_value = :email
                        AND CASE principal.principal_type
                                WHEN 'CONSUMER' THEN 'SHOP'
                                ELSE 'BUSINESS'
                            END = :realm
                    """
                ),
                {"channel": channel, "email": normalized_email, "realm": realm},
            ).one_or_none()
        return _identity_from_row(row) if row is not None else None

    def recent_request_times(
        self, normalized_email_hash: bytes, realm: AuthRealm, since: datetime
    ) -> tuple[datetime, ...]:
        with self.engine.connect() as connection:
            rows: tuple[datetime, ...] = tuple(
                connection.execute(
                    text(
                        """
                        SELECT requested_at
                        FROM email_otp_requests
                        WHERE normalized_email_hash = :email_hash
                          AND auth_realm = :realm
                          AND requested_at >= :since
                        ORDER BY requested_at
                        """
                    ),
                    {"email_hash": normalized_email_hash, "realm": realm, "since": since},
                ).scalars()
            )
        return rows

    def record_request(
        self, normalized_email_hash: bytes, realm: AuthRealm, requested_at: datetime
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO email_otp_requests
                        (normalized_email_hash, auth_realm, requested_at)
                    VALUES
                        (:email_hash, :realm, :requested_at)
                    """
                ),
                {
                    "email_hash": normalized_email_hash,
                    "realm": realm,
                    "requested_at": requested_at,
                },
            )

    def create_challenge(self, challenge: EmailOtpChallenge) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO email_otp_challenges
                        (challenge_id, identity_id, code_hash, attempts, expires_at, consumed_at)
                    VALUES
                        (:challenge, :identity, :code_hash, :attempts, :expires_at, :consumed_at)
                    """
                ),
                {
                    "challenge": challenge.challenge_id,
                    "identity": challenge.identity_id,
                    "code_hash": challenge.code_hash,
                    "attempts": challenge.attempts,
                    "expires_at": challenge.expires_at,
                    "consumed_at": challenge.consumed_at,
                },
            )

    def get_challenge(self, challenge_id: UUID) -> EmailOtpChallenge | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT challenge_id, identity_id, code_hash, attempts, expires_at, consumed_at
                    FROM email_otp_challenges
                    WHERE challenge_id = :challenge
                    """
                    ),
                    {"challenge": challenge_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return EmailOtpChallenge(
            challenge_id=row["challenge_id"],
            identity_id=row["identity_id"],
            code_hash=row["code_hash"],
            attempts=row["attempts"],
            expires_at=row["expires_at"],
            consumed_at=row["consumed_at"],
        )

    def get_identity(self, identity_id: UUID) -> OtpIdentity | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(IDENTITY_SELECT + " WHERE identity.identity_id = :identity"),
                {"identity": identity_id},
            ).one_or_none()
        return _identity_from_row(row) if row is not None else None

    def record_failure(self, challenge_id: UUID, attempts: int) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE email_otp_challenges
                    SET attempts = LEAST(:attempts, 5), updated_at = now()
                    WHERE challenge_id = :challenge AND consumed_at IS NULL
                    """
                ),
                {"challenge": challenge_id, "attempts": attempts},
            )

    def consume_challenge(self, challenge_id: UUID, consumed_at: datetime) -> bool:
        with self.engine.begin() as connection:
            consumed = connection.execute(
                text(
                    """
                    UPDATE email_otp_challenges
                    SET consumed_at = :consumed_at, updated_at = :consumed_at
                    WHERE challenge_id = :challenge AND consumed_at IS NULL
                    RETURNING challenge_id
                    """
                ),
                {"challenge": challenge_id, "consumed_at": consumed_at},
            ).scalar_one_or_none()
        return consumed is not None

    def mark_identity_verified(self, identity_id: UUID, verified_at: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE principal_identities
                    SET verified_at = COALESCE(verified_at, :verified_at), updated_at = :verified_at
                    WHERE identity_id = :identity
                    """
                ),
                {"identity": identity_id, "verified_at": verified_at},
            )

    def create_session(
        self,
        *,
        identity: OtpIdentity,
        session_token_hash: bytes,
        csrf_token_hash: bytes,
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO sessions
                        (
                            account_id,
                            principal_id,
                            auth_realm,
                            session_token_hash,
                            csrf_token_hash,
                            expires_at,
                            created_at,
                            updated_at
                        )
                    VALUES
                        (
                            :account,
                            :principal,
                            :realm,
                            :session_hash,
                            :csrf_hash,
                            :expires_at,
                            :created_at,
                            :created_at
                        )
                    """
                ),
                {
                    "account": identity.account_id,
                    "principal": identity.principal_id,
                    "realm": identity.realm,
                    "session_hash": session_token_hash,
                    "csrf_hash": csrf_token_hash,
                    "expires_at": expires_at,
                    "created_at": created_at,
                },
            )


class DevelopmentPostgresOtpStore(PostgresEmailOtpStore):
    """Local-only identity bootstrap for fixed-code email or phone authentication."""

    def resolve_identity(self, normalized_email: str, realm: AuthRealm) -> OtpIdentity | None:
        channel = "EMAIL" if "@" in normalized_email else "PHONE"
        legacy_destination = (
            normalized_email[3:]
            if channel == "PHONE"
            and normalized_email.startswith("+91")
            and len(normalized_email) == 13
            else normalized_email
        )
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"{channel}:{normalized_email}:{realm}"},
            )
            identity_lookup = (
                IDENTITY_SELECT  # noqa: S608 - static SQL with bound parameters
                + """
                      WHERE identity.channel = :channel
                        AND identity.normalized_value IN (:destination, :legacy_destination)
                        AND CASE principal.principal_type
                                WHEN 'CONSUMER' THEN 'SHOP'
                                ELSE 'BUSINESS'
                            END = :realm
                      ORDER BY EXISTS (
                          SELECT 1 FROM person_profiles profile
                          WHERE profile.account_id=identity.account_id
                            AND profile.status='ACTIVE'
                      ) DESC,
                      (identity.normalized_value=:destination) DESC
                      LIMIT 1
                    """
            )
            row = connection.execute(
                text(identity_lookup),
                {
                    "channel": channel,
                    "destination": normalized_email,
                    "legacy_destination": legacy_destination,
                    "realm": realm,
                },
            ).one_or_none()
            if row is not None:
                return _identity_from_row(row)
            if realm != "SHOP":
                return None

            account_id, principal_id, identity_id = uuid4(), uuid4(), uuid4()
            connection.execute(
                text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
                {"account": account_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO principals
                        (principal_id, account_id, account_kind, principal_type)
                    VALUES
                        (:principal, :account, 'CONSUMER', 'CONSUMER')
                    """
                ),
                {"principal": principal_id, "account": account_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO principal_identities
                        (identity_id, account_id, principal_id, channel, normalized_value)
                    VALUES
                        (:identity, :account, :principal, :channel, :destination)
                    """
                ),
                {
                    "identity": identity_id,
                    "account": account_id,
                    "principal": principal_id,
                    "channel": channel,
                    "destination": normalized_email,
                },
            )
        return OtpIdentity(
            identity_id,
            principal_id,
            account_id,
            normalized_email,
            "SHOP",
            "ACTIVE",
        )


class PostgresBrowserSessionStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def find_by_token_hash(self, token_hash: bytes) -> BrowserSession | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT
                        session_id,
                        account_id,
                        principal_id,
                        auth_realm,
                        session_token_hash,
                        csrf_token_hash,
                        COALESCE(rotated_at, created_at) AS credential_created_at,
                        expires_at,
                        revoked_at
                    FROM sessions
                    WHERE session_token_hash = :token_hash
                    """
                    ),
                    {"token_hash": token_hash},
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["session_token_hash"] is None or row["csrf_token_hash"] is None:
            return None
        return BrowserSession(
            session_id=row["session_id"],
            account_id=row["account_id"],
            principal_id=row["principal_id"],
            realm=row["auth_realm"],
            token_hash=row["session_token_hash"],
            csrf_hash=row["csrf_token_hash"],
            created_at=row["credential_created_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    def replace_tokens(
        self,
        session_id: UUID,
        *,
        token_hash: bytes,
        csrf_hash: bytes,
        expires_at: datetime,
        rotated_at: datetime,
    ) -> bool:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    """
                    UPDATE sessions
                    SET session_token_hash = :token_hash,
                        csrf_token_hash = :csrf_hash,
                        expires_at = :expires_at,
                        rotated_at = :rotated_at,
                        updated_at = :rotated_at
                    WHERE session_id = :session
                      AND revoked_at IS NULL
                      AND expires_at > :rotated_at
                    RETURNING session_id
                    """
                ),
                {
                    "session": session_id,
                    "token_hash": token_hash,
                    "csrf_hash": csrf_hash,
                    "expires_at": expires_at,
                    "rotated_at": rotated_at,
                },
            ).scalar_one_or_none()
        return updated is not None

    def revoke(self, session_id: UUID, revoked_at: datetime) -> bool:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    """
                    UPDATE sessions
                    SET revoked_at = :revoked_at, updated_at = :revoked_at
                    WHERE session_id = :session AND revoked_at IS NULL
                    RETURNING session_id
                    """
                ),
                {"session": session_id, "revoked_at": revoked_at},
            ).scalar_one_or_none()
        return updated is not None

    def revoke_principal(self, principal_id: UUID, revoked_at: datetime) -> int:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE sessions
                    SET revoked_at = :revoked_at, updated_at = :revoked_at
                    WHERE principal_id = :principal AND revoked_at IS NULL
                    """
                ),
                {"principal": principal_id, "revoked_at": revoked_at},
            )
        return result.rowcount

    def replace_csrf(self, session_id: UUID, csrf_hash: bytes, updated_at: datetime) -> bool:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    """UPDATE sessions SET csrf_token_hash=:csrf_hash, updated_at=:updated_at
                    WHERE session_id=:session AND revoked_at IS NULL
                      AND expires_at > :updated_at
                    RETURNING session_id"""
                ),
                {"session": session_id, "csrf_hash": csrf_hash, "updated_at": updated_at},
            ).scalar_one_or_none()
        return updated is not None
