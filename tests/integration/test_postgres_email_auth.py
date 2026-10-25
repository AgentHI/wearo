from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text

from apps.api.wearo_api.browser_sessions import (
    BrowserSessionService,
    SessionAuthenticationError,
    SessionPolicy,
)
from apps.api.wearo_api.database import normalize_database_url
from apps.api.wearo_api.email_otp import (
    AuthRealm,
    EmailOtpPolicy,
    EmailOtpService,
    OtpAuthenticationError,
)
from apps.api.wearo_api.postgres_auth import (
    DevelopmentPostgresOtpStore,
    PostgresBrowserSessionStore,
    PostgresEmailOtpStore,
)

pytestmark = pytest.mark.integration

PEPPER = b"postgres-auth-test-pepper-32-bytes"


class RecordingProvider:
    def __init__(self) -> None:
        self.code = ""

    def send_sign_in_code(
        self, *, to_email: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None:
        assert to_email == "integration@example.com"
        assert realm == "SHOP"
        assert expires_at > datetime.now(UTC)
        self.code = code


@pytest.fixture
def engine() -> Iterator[Engine]:
    raw_url = os.environ.get("WEARO_DATABASE_URL")
    if raw_url is None:
        pytest.skip("WEARO_DATABASE_URL is required for PostgreSQL integration tests")
    database_engine = create_engine(normalize_database_url(raw_url))
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def test_postgres_otp_creates_real_authenticated_csrf_session(engine: Engine) -> None:
    account_id, principal_id, identity_id = uuid4(), uuid4(), uuid4()
    email = "integration@example.com"
    now = datetime.now(UTC)
    email_hash = hmac.new(PEPPER, b"email\0" + email.encode(), hashlib.sha256).digest()
    with engine.begin() as connection:
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
                    (:identity, :account, :principal, 'EMAIL', :email)
                """
            ),
            {
                "identity": identity_id,
                "account": account_id,
                "principal": principal_id,
                "email": email,
            },
        )

    try:
        provider = RecordingProvider()
        otp = EmailOtpService(
            PostgresEmailOtpStore(engine),
            provider,
            EmailOtpPolicy(),
            pepper=PEPPER,
        )
        challenge = otp.request_code(email, "SHOP", now=now)
        result = otp.verify_code(challenge.challenge_id, provider.code, now=now)

        sessions = BrowserSessionService(
            PostgresBrowserSessionStore(engine), SessionPolicy(), pepper=PEPPER
        )
        authenticated = sessions.authenticate(
            result.session_token,
            expected_realm="SHOP",
            csrf_token=result.csrf_token,
            mutation=True,
            now=now,
        )
        assert authenticated.account_id == account_id
        assert authenticated.principal_id == principal_id
        invalid_csrf = "wrong"
        with pytest.raises(SessionAuthenticationError):
            sessions.authenticate(
                result.session_token,
                expected_realm="SHOP",
                csrf_token=invalid_csrf,
                mutation=True,
                now=now,
            )
        with pytest.raises(OtpAuthenticationError):
            otp.verify_code(challenge.challenge_id, provider.code, now=now)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM sessions WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM principal_identities WHERE identity_id = :identity"),
                {"identity": identity_id},
            )
            connection.execute(
                text("DELETE FROM principals WHERE principal_id = :principal"),
                {"principal": principal_id},
            )
            connection.execute(
                text("DELETE FROM accounts WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM email_otp_requests WHERE normalized_email_hash = :email_hash"),
                {"email_hash": email_hash},
            )


def test_development_fixed_code_bootstraps_email_and_phone_identities(engine: Engine) -> None:
    destinations = ("local-test@example.com", "+919876543210")
    normalized_hashes = [
        hmac.new(PEPPER, b"email\0" + destination.encode(), hashlib.sha256).digest()
        for destination in destinations
    ]
    created_accounts: list[object] = []
    service = EmailOtpService(
        DevelopmentPostgresOtpStore(engine),
        RecordingProvider(),
        EmailOtpPolicy(resend_cooldown=datetime.resolution),
        pepper=PEPPER,
        fixed_test_code="1324",
    )
    try:
        for destination in destinations:
            challenge = service.request_code(destination, "SHOP")
            session = service.verify_code(challenge.challenge_id, "1324")
            created_accounts.append(session.account_id)

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT channel, normalized_value
                    FROM principal_identities
                    WHERE account_id = ANY(:accounts)
                    ORDER BY channel
                    """
                ),
                {"accounts": created_accounts},
            ).all()
        assert rows == [("EMAIL", destinations[0]), ("PHONE", destinations[1])]
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM sessions WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM principal_identities WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM principals WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM accounts WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM email_otp_requests WHERE normalized_email_hash = ANY(:hashes)"),
                {"hashes": normalized_hashes},
            )


def test_signup_after_permanent_deletion_creates_a_new_empty_account(engine: Engine) -> None:
    old_account_id, old_principal_id, old_identity_id = uuid4(), uuid4(), uuid4()
    destination = "returning-after-deletion@example.com"
    destination_hash = hmac.new(PEPPER, b"email\0" + destination.encode(), hashlib.sha256).digest()
    now = datetime.now(UTC)
    cancelled_at = now - timedelta(days=31)
    deletion_at = cancelled_at + timedelta(days=30)
    created_accounts: list[object] = [old_account_id]
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO accounts
                    (account_id, kind, status, cancellation_at, deletion_at,
                     permanently_deleted_at, deletion_outcome)
                VALUES
                    (:account, 'CONSUMER', 'PERMANENTLY_DELETED', :cancelled_at,
                     :deletion_at, :permanently_deleted_at, 'COMPLETED')
                """
            ),
            {
                "account": old_account_id,
                "cancelled_at": cancelled_at,
                "deletion_at": deletion_at,
                "permanently_deleted_at": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO principals
                    (principal_id, account_id, account_kind, principal_type, status)
                VALUES (:principal, :account, 'CONSUMER', 'CONSUMER', 'CLOSED')
                """
            ),
            {"principal": old_principal_id, "account": old_account_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO principal_identities
                    (identity_id, account_id, principal_id, channel, normalized_value)
                VALUES (:identity, :account, :principal, 'EMAIL', :destination)
                """
            ),
            {
                "identity": old_identity_id,
                "account": old_account_id,
                "principal": old_principal_id,
                "destination": destination,
            },
        )

    service = EmailOtpService(
        DevelopmentPostgresOtpStore(engine),
        RecordingProvider(),
        EmailOtpPolicy(resend_cooldown=datetime.resolution),
        pepper=PEPPER,
        fixed_test_code="1324",
    )
    try:
        challenge = service.request_code(destination, "SHOP", now=now)
        new_session = service.verify_code(challenge.challenge_id, "1324", now=now)
        created_accounts.append(new_session.account_id)

        assert new_session.account_id != old_account_id
        assert new_session.principal_id != old_principal_id
        with engine.connect() as connection:
            new_account: str = connection.execute(
                text("SELECT status FROM accounts WHERE account_id=:account"),
                {"account": new_session.account_id},
            ).scalar_one()
            personal_rows = (
                connection.execute(
                    text(
                        """
                    SELECT
                      (SELECT count(*) FROM person_profiles WHERE account_id=:account)
                        AS profiles,
                      (SELECT count(*) FROM media_assets WHERE account_id=:account) AS media,
                      (SELECT count(*) FROM render_jobs WHERE account_id=:account) AS try_ons
                    """
                    ),
                    {"account": new_session.account_id},
                )
                .mappings()
                .one()
            )
        assert new_account == "ACTIVE"
        assert dict(personal_rows) == {"profiles": 0, "media": 0, "try_ons": 0}
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM sessions WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM principal_identities WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM principals WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM accounts WHERE account_id = ANY(:accounts)"),
                {"accounts": created_accounts},
            )
            connection.execute(
                text("DELETE FROM email_otp_requests WHERE normalized_email_hash = :email_hash"),
                {"email_hash": destination_hash},
            )
