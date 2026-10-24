from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

SessionRealm = Literal["SHOP", "BUSINESS"]


class SessionAuthenticationError(ValueError):
    """Generic browser-session denial."""


@dataclass(frozen=True)
class SessionPolicy:
    ttl: timedelta = timedelta(days=30)
    rotate_after: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        if self.ttl <= timedelta(0) or self.rotate_after <= timedelta(0):
            raise ValueError("session durations must be positive")
        if self.rotate_after >= self.ttl:
            raise ValueError("rotation must occur before expiry")


@dataclass(frozen=True)
class BrowserSession:
    session_id: UUID
    account_id: UUID
    principal_id: UUID
    realm: SessionRealm
    token_hash: bytes
    csrf_hash: bytes
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class SessionCredentials:
    session_token: str
    csrf_token: str
    expires_at: datetime


class BrowserSessionStore(Protocol):
    def find_by_token_hash(self, token_hash: bytes) -> BrowserSession | None: ...

    def replace_tokens(
        self,
        session_id: UUID,
        *,
        token_hash: bytes,
        csrf_hash: bytes,
        expires_at: datetime,
        rotated_at: datetime,
    ) -> bool: ...

    def revoke(self, session_id: UUID, revoked_at: datetime) -> bool: ...

    def revoke_principal(self, principal_id: UUID, revoked_at: datetime) -> int: ...

    def replace_csrf(self, session_id: UUID, csrf_hash: bytes, updated_at: datetime) -> bool: ...


class BrowserSessionService:
    def __init__(self, store: BrowserSessionStore, policy: SessionPolicy, *, pepper: bytes) -> None:
        if len(pepper) < 32:
            raise ValueError("session pepper must contain at least 32 bytes")
        self.store = store
        self.policy = policy
        self.pepper = pepper

    def _hash(self, purpose: bytes, value: str) -> bytes:
        return hmac.new(self.pepper, purpose + b"\0" + value.encode(), hashlib.sha256).digest()

    def authenticate(
        self,
        session_token: str,
        *,
        expected_realm: SessionRealm,
        csrf_token: str | None = None,
        mutation: bool = False,
        now: datetime | None = None,
    ) -> BrowserSession:
        current = now or datetime.now(UTC)
        session = self.store.find_by_token_hash(self._hash(b"session", session_token))
        valid = (
            session is not None
            and session.realm == expected_realm
            and session.revoked_at is None
            and session.expires_at > current
        )
        csrf_valid = not mutation or (
            csrf_token is not None
            and session is not None
            and hmac.compare_digest(session.csrf_hash, self._hash(b"csrf", csrf_token))
        )
        if not valid or not csrf_valid or session is None:
            raise SessionAuthenticationError("invalid or expired session")
        return session

    def rotate(self, session_token: str, *, now: datetime | None = None) -> SessionCredentials:
        current = now or datetime.now(UTC)
        session = self.authenticate(
            session_token, expected_realm=self._realm(session_token), now=current
        )
        if current - session.created_at < self.policy.rotate_after:
            raise SessionAuthenticationError("session is not eligible for rotation")
        new_token = secrets.token_urlsafe(32)
        new_csrf = secrets.token_urlsafe(32)
        expires_at = current + self.policy.ttl
        if not self.store.replace_tokens(
            session.session_id,
            token_hash=self._hash(b"session", new_token),
            csrf_hash=self._hash(b"csrf", new_csrf),
            expires_at=expires_at,
            rotated_at=current,
        ):
            raise SessionAuthenticationError("invalid or expired session")
        return SessionCredentials(new_token, new_csrf, expires_at)

    def logout(self, session_token: str, csrf_token: str, *, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        realm = self._realm(session_token)
        session = self.authenticate(
            session_token,
            expected_realm=realm,
            csrf_token=csrf_token,
            mutation=True,
            now=current,
        )
        if not self.store.revoke(session.session_id, current):
            raise SessionAuthenticationError("invalid or expired session")

    def revoke_all(self, principal_id: UUID, *, now: datetime | None = None) -> int:
        return self.store.revoke_principal(principal_id, now or datetime.now(UTC))

    def refresh_csrf(
        self,
        session_token: str,
        *,
        expected_realm: SessionRealm,
        now: datetime | None = None,
    ) -> str:
        current = now or datetime.now(UTC)
        session = self.authenticate(session_token, expected_realm=expected_realm, now=current)
        csrf_token = secrets.token_urlsafe(32)
        if not self.store.replace_csrf(
            session.session_id, self._hash(b"csrf", csrf_token), current
        ):
            raise SessionAuthenticationError("invalid or expired session")
        return csrf_token

    def _realm(self, session_token: str) -> SessionRealm:
        session = self.store.find_by_token_hash(self._hash(b"session", session_token))
        if session is None:
            raise SessionAuthenticationError("invalid or expired session")
        return session.realm


def session_cookie(token: str, max_age_seconds: int) -> str:
    return (
        f"wearo_session={token}; Path=/; Max-Age={max_age_seconds}; HttpOnly; Secure; SameSite=Lax"
    )
