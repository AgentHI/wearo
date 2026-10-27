from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class PlatformAdminConfigurationError(RuntimeError):
    """Raised when the single MVP administrator has not been configured."""


@dataclass(frozen=True)
class PlatformAdminSession:
    token: str
    csrf_token: str
    expires_at: datetime


@dataclass
class _StoredSession:
    csrf_hash: bytes
    expires_at: datetime


@dataclass
class _FailureWindow:
    attempts: int
    locked_until: datetime | None


class PlatformAdminAuth:
    """Isolated, single-account authentication for the India MVP admin console."""

    def __init__(
        self,
        email: str,
        password: str,
        *,
        session_ttl: timedelta = timedelta(minutes=30),
        max_attempts: int = 5,
        lockout: timedelta = timedelta(minutes=15),
    ) -> None:
        if not email.strip() or not password:
            raise PlatformAdminConfigurationError(
                "WEARO_ADMIN_EMAIL and WEARO_ADMIN_PASSWORD must both be configured"
            )
        self._email = email.strip().casefold()
        self._password_digest = self._digest(password)
        self._session_ttl = session_ttl
        self._max_attempts = max_attempts
        self._lockout = lockout
        self._sessions: dict[bytes, _StoredSession] = {}
        self._failures: dict[str, _FailureWindow] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8")).digest()

    def login(
        self, email: str, password: str, client_key: str, *, now: datetime | None = None
    ) -> PlatformAdminSession | None:
        current = now or datetime.now(UTC)
        key = f"{client_key}:{email.strip().casefold()}"
        with self._lock:
            failure = self._failures.get(key)
            if failure and failure.locked_until and failure.locked_until > current:
                return None

            email_matches = hmac.compare_digest(email.strip().casefold(), self._email)
            password_matches = hmac.compare_digest(self._digest(password), self._password_digest)
            if not (email_matches and password_matches):
                attempts = (failure.attempts if failure else 0) + 1
                locked_until = current + self._lockout if attempts >= self._max_attempts else None
                self._failures[key] = _FailureWindow(attempts, locked_until)
                return None

            self._failures.pop(key, None)
            token = secrets.token_urlsafe(48)
            csrf_token = secrets.token_urlsafe(32)
            expires_at = current + self._session_ttl
            self._sessions[self._digest(token)] = _StoredSession(
                csrf_hash=self._digest(csrf_token), expires_at=expires_at
            )
            return PlatformAdminSession(token, csrf_token, expires_at)

    def authenticate(self, token: str, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        token_hash = self._digest(token)
        with self._lock:
            session = self._sessions.get(token_hash)
            if session is None:
                return False
            if session.expires_at <= current:
                self._sessions.pop(token_hash, None)
                return False
            return True

    def logout(self, token: str, csrf_token: str) -> bool:
        token_hash = self._digest(token)
        with self._lock:
            session = self._sessions.get(token_hash)
            if session is None or not hmac.compare_digest(
                session.csrf_hash, self._digest(csrf_token)
            ):
                return False
            self._sessions.pop(token_hash, None)
            return True

    def invalidate(self, token: str) -> bool:
        """Invalidate a session for the same-site logout endpoint."""
        with self._lock:
            return self._sessions.pop(self._digest(token), None) is not None
