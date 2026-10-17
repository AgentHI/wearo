from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4


class AuthenticationError(ValueError):
    """Generic admin authentication failure that discloses no account state."""


@dataclass(frozen=True)
class AdminAuthPolicy:
    max_password_attempts: int
    password_lockout: timedelta
    challenge_ttl: timedelta
    max_mfa_attempts: int
    session_ttl: timedelta
    totp_step_seconds: int = 30
    totp_window: int = 1

    def __post_init__(self) -> None:
        if min(self.max_password_attempts, self.max_mfa_attempts, self.totp_step_seconds) < 1:
            raise ValueError("authentication limits must be positive")
        if min(self.password_lockout, self.challenge_ttl, self.session_ttl) <= timedelta(0):
            raise ValueError("authentication durations must be positive")
        if self.totp_window < 0:
            raise ValueError("totp_window cannot be negative")


@dataclass(frozen=True)
class AdminIdentity:
    admin_id: UUID
    username: str
    password_hash: bytes
    mfa_secret_encrypted: bytes
    scopes: tuple[str, ...]
    status: str
    failed_attempts: int
    locked_until: datetime | None


@dataclass(frozen=True)
class MfaChallenge:
    challenge_id: UUID
    admin_id: UUID
    attempts: int
    expires_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True)
class ChallengeResult:
    challenge_id: UUID
    expires_at: datetime


@dataclass(frozen=True)
class AdminSessionResult:
    admin_id: UUID
    session_token: str
    csrf_token: str
    scopes: tuple[str, ...]
    expires_at: datetime


class SecretCipher(Protocol):
    def decrypt(self, ciphertext: bytes) -> bytes: ...


class AdminAuthStore(Protocol):
    def find_admin(self, normalized_username: str) -> AdminIdentity | None: ...

    def get_admin(self, admin_id: UUID) -> AdminIdentity | None: ...

    def record_password_failure(
        self, admin_id: UUID, *, failed_attempts: int, locked_until: datetime | None
    ) -> None: ...

    def record_password_success(self, admin_id: UUID, authenticated_at: datetime) -> None: ...

    def create_challenge(self, challenge: MfaChallenge, token_hash: bytes) -> None: ...

    def get_challenge(self, challenge_id: UUID) -> MfaChallenge | None: ...

    def record_mfa_failure(self, challenge_id: UUID, attempts: int) -> None: ...

    def consume_challenge(self, challenge_id: UUID, consumed_at: datetime) -> bool: ...

    def create_session(
        self,
        *,
        admin_id: UUID,
        session_token_hash: bytes,
        csrf_token_hash: bytes,
        scopes: tuple[str, ...],
        expires_at: datetime,
        created_at: datetime,
    ) -> None: ...

    def consume_recovery_code(
        self, admin_id: UUID, code_hash: bytes, used_at: datetime
    ) -> bool: ...


class AuditSink(Protocol):
    def record(
        self, *, actor_id: UUID | None, action: str, target_id: UUID | None, occurred_at: datetime
    ) -> None: ...


def hash_password(password: str, *, salt: bytes | None = None) -> bytes:
    if not password:
        raise ValueError("password cannot be empty")
    actual_salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=actual_salt, n=2**14, r=8, p=1, dklen=32
    )
    return b"scrypt$16384$8$1$" + base64.b64encode(actual_salt) + b"$" + base64.b64encode(derived)


def verify_password(password: str, encoded: bytes) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split(b"$")
        if algorithm != b"scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(expected)),
        )
        return hmac.compare_digest(derived, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def hash_secret(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def totp_code(secret: bytes, at: datetime, *, step_seconds: int = 30) -> str:
    counter = int(at.timestamp()) // step_seconds
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def verify_totp(secret: bytes, code: str, at: datetime, *, step_seconds: int, window: int) -> bool:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return False
    return any(
        hmac.compare_digest(
            totp_code(
                secret, at + timedelta(seconds=offset * step_seconds), step_seconds=step_seconds
            ),
            code,
        )
        for offset in range(-window, window + 1)
    )


class AdminAuthService:
    def __init__(
        self,
        store: AdminAuthStore,
        cipher: SecretCipher,
        audit: AuditSink,
        policy: AdminAuthPolicy,
    ) -> None:
        self.store = store
        self.cipher = cipher
        self.audit = audit
        self.policy = policy
        self._dummy_password_hash = hash_password(
            "not-a-real-admin-password", salt=b"wearo-admin-dmy"
        )

    def begin_password_login(
        self, username: str, password: str, *, now: datetime | None = None
    ) -> ChallengeResult:
        current = now or datetime.now(UTC)
        normalized = username.strip().casefold()
        admin = self.store.find_admin(normalized)
        candidate_hash = admin.password_hash if admin is not None else self._dummy_password_hash
        password_valid = verify_password(password, candidate_hash)
        if (
            admin is None
            or admin.status != "ACTIVE"
            or (admin.locked_until is not None and admin.locked_until > current)
            or not password_valid
        ):
            if admin is not None:
                attempts = admin.failed_attempts + 1
                locked_until = (
                    current + self.policy.password_lockout
                    if attempts >= self.policy.max_password_attempts
                    else None
                )
                self.store.record_password_failure(
                    admin.admin_id, failed_attempts=attempts, locked_until=locked_until
                )
                self.audit.record(
                    actor_id=admin.admin_id,
                    action="admin.password_login_failed",
                    target_id=admin.admin_id,
                    occurred_at=current,
                )
            raise AuthenticationError("invalid administrator credentials")

        self.store.record_password_success(admin.admin_id, current)
        challenge = MfaChallenge(
            challenge_id=uuid4(),
            admin_id=admin.admin_id,
            attempts=0,
            expires_at=current + self.policy.challenge_ttl,
            consumed_at=None,
        )
        self.store.create_challenge(challenge, hash_secret(secrets.token_urlsafe(32)))
        self.audit.record(
            actor_id=admin.admin_id,
            action="admin.mfa_challenge_created",
            target_id=challenge.challenge_id,
            occurred_at=current,
        )
        return ChallengeResult(challenge.challenge_id, challenge.expires_at)

    def complete_mfa(
        self, challenge_id: UUID, code: str, *, now: datetime | None = None
    ) -> AdminSessionResult:
        current = now or datetime.now(UTC)
        challenge = self.store.get_challenge(challenge_id)
        if challenge is None:
            raise AuthenticationError("invalid or expired MFA challenge")
        admin = self.store.get_admin(challenge.admin_id)
        valid_challenge = (
            admin is not None
            and admin.status == "ACTIVE"
            and challenge.consumed_at is None
            and challenge.expires_at > current
            and challenge.attempts < self.policy.max_mfa_attempts
        )
        valid_code = False
        if valid_challenge and admin is not None:
            secret = self.cipher.decrypt(admin.mfa_secret_encrypted)
            valid_code = verify_totp(
                secret,
                code,
                current,
                step_seconds=self.policy.totp_step_seconds,
                window=self.policy.totp_window,
            )
        if not valid_challenge or not valid_code or admin is None:
            if challenge.attempts < self.policy.max_mfa_attempts:
                self.store.record_mfa_failure(challenge_id, challenge.attempts + 1)
            self.audit.record(
                actor_id=challenge.admin_id,
                action="admin.mfa_failed",
                target_id=challenge_id,
                occurred_at=current,
            )
            raise AuthenticationError("invalid or expired MFA challenge")
        if not self.store.consume_challenge(challenge_id, current):
            raise AuthenticationError("invalid or expired MFA challenge")
        return self._create_session(admin, current)

    def complete_recovery(
        self, challenge_id: UUID, recovery_code: str, *, now: datetime | None = None
    ) -> AdminSessionResult:
        current = now or datetime.now(UTC)
        challenge = self.store.get_challenge(challenge_id)
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= current
        ):
            raise AuthenticationError("invalid or expired recovery challenge")
        admin = self.store.get_admin(challenge.admin_id)
        if (
            admin is None
            or admin.status != "ACTIVE"
            or not self.store.consume_recovery_code(
                admin.admin_id, hash_secret(recovery_code), current
            )
        ):
            raise AuthenticationError("invalid or expired recovery challenge")
        if not self.store.consume_challenge(challenge_id, current):
            raise AuthenticationError("invalid or expired recovery challenge")
        self.audit.record(
            actor_id=admin.admin_id,
            action="admin.recovery_code_used",
            target_id=challenge_id,
            occurred_at=current,
        )
        return self._create_session(admin, current)

    def _create_session(self, admin: AdminIdentity, current: datetime) -> AdminSessionResult:
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = current + self.policy.session_ttl
        self.store.create_session(
            admin_id=admin.admin_id,
            session_token_hash=hash_secret(session_token),
            csrf_token_hash=hash_secret(csrf_token),
            scopes=admin.scopes,
            expires_at=expires_at,
            created_at=current,
        )
        self.audit.record(
            actor_id=admin.admin_id,
            action="admin.session_created",
            target_id=admin.admin_id,
            occurred_at=current,
        )
        return AdminSessionResult(
            admin_id=admin.admin_id,
            session_token=session_token,
            csrf_token=csrf_token,
            scopes=admin.scopes,
            expires_at=expires_at,
        )
