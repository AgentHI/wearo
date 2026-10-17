from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID, uuid4

AuthRealm = Literal["SHOP", "BUSINESS"]


class OtpAuthenticationError(ValueError):
    """Generic OTP failure that discloses no identity or challenge state."""


@dataclass(frozen=True)
class EmailOtpPolicy:
    challenge_ttl: timedelta = timedelta(minutes=10)
    resend_cooldown: timedelta = timedelta(seconds=60)
    max_requests_per_window: int = 5
    request_window: timedelta = timedelta(hours=1)
    max_verification_attempts: int = 5
    session_ttl: timedelta = timedelta(days=7)

    def __post_init__(self) -> None:
        if min(self.max_requests_per_window, self.max_verification_attempts) < 1:
            raise ValueError("OTP limits must be positive")
        if min(
            self.challenge_ttl,
            self.resend_cooldown,
            self.request_window,
            self.session_ttl,
        ) <= timedelta(0):
            raise ValueError("OTP durations must be positive")


@dataclass(frozen=True)
class OtpIdentity:
    identity_id: UUID
    principal_id: UUID
    account_id: UUID
    normalized_email: str
    realm: AuthRealm
    status: str


@dataclass(frozen=True)
class EmailOtpChallenge:
    challenge_id: UUID
    identity_id: UUID
    code_hash: bytes
    attempts: int
    expires_at: datetime
    consumed_at: datetime | None = None


@dataclass(frozen=True)
class OtpRequestResult:
    challenge_id: UUID
    expires_at: datetime
    message: str = "If the address is eligible, a sign-in code has been sent."


@dataclass(frozen=True)
class OtpSessionResult:
    principal_id: UUID
    account_id: UUID
    realm: AuthRealm
    session_token: str
    csrf_token: str
    expires_at: datetime


class EmailOtpStore(Protocol):
    def resolve_identity(self, normalized_email: str, realm: AuthRealm) -> OtpIdentity | None: ...

    def recent_request_times(
        self, normalized_email_hash: bytes, realm: AuthRealm, since: datetime
    ) -> tuple[datetime, ...]: ...

    def record_request(
        self, normalized_email_hash: bytes, realm: AuthRealm, requested_at: datetime
    ) -> None: ...

    def create_challenge(self, challenge: EmailOtpChallenge) -> None: ...

    def get_challenge(self, challenge_id: UUID) -> EmailOtpChallenge | None: ...

    def get_identity(self, identity_id: UUID) -> OtpIdentity | None: ...

    def record_failure(self, challenge_id: UUID, attempts: int) -> None: ...

    def consume_challenge(self, challenge_id: UUID, consumed_at: datetime) -> bool: ...

    def mark_identity_verified(self, identity_id: UUID, verified_at: datetime) -> None: ...

    def create_session(
        self,
        *,
        identity: OtpIdentity,
        session_token_hash: bytes,
        csrf_token_hash: bytes,
        expires_at: datetime,
        created_at: datetime,
    ) -> None: ...


class EmailDeliveryProvider(Protocol):
    def send_sign_in_code(
        self, *, to_email: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None: ...


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if len(normalized) > 320 or normalized.count("@") != 1:
        return ""
    local, domain = normalized.split("@")
    if not local or not domain or "." not in domain or any(char.isspace() for char in normalized):
        return ""
    return normalized


def normalize_test_destination(value: str) -> str:
    """Normalize an email or phone identifier for explicitly enabled local test auth."""
    email = normalize_email(value)
    if email:
        return email
    compact = value.strip()
    if not compact or any(character.isalpha() for character in compact):
        return ""
    if any(character not in "+-(). 0123456789" for character in compact):
        return ""
    if "+" in compact and not compact.startswith("+"):
        return ""
    digits = "".join(character for character in compact if character.isdigit())
    if not 7 <= len(digits) <= 15:
        return ""
    return f"+{digits}" if compact.startswith("+") else digits


def _secret_hash(pepper: bytes, purpose: bytes, value: str) -> bytes:
    return hmac.new(pepper, purpose + b"\0" + value.encode(), hashlib.sha256).digest()


class EmailOtpService:
    def __init__(
        self,
        store: EmailOtpStore,
        provider: EmailDeliveryProvider,
        policy: EmailOtpPolicy,
        *,
        pepper: bytes,
        fixed_test_code: str | None = None,
    ) -> None:
        if len(pepper) < 32:
            raise ValueError("OTP pepper must contain at least 32 bytes")
        self.store = store
        self.provider = provider
        self.policy = policy
        self.pepper = pepper
        if fixed_test_code is not None and (
            not 4 <= len(fixed_test_code) <= 8
            or not fixed_test_code.isascii()
            or not fixed_test_code.isdigit()
        ):
            raise ValueError("fixed test OTP must contain 4 to 8 ASCII digits")
        self.fixed_test_code = fixed_test_code

    def request_code(
        self, email: str, realm: AuthRealm, *, now: datetime | None = None
    ) -> OtpRequestResult:
        current = now or datetime.now(UTC)
        public_challenge_id = uuid4()
        public_expiry = current + self.policy.challenge_ttl
        normalized = (
            normalize_test_destination(email) if self.fixed_test_code else normalize_email(email)
        )
        email_hash = _secret_hash(self.pepper, b"email", normalized or "invalid")
        recent = self.store.recent_request_times(
            email_hash, realm, current - self.policy.request_window
        )
        allowed = self.fixed_test_code is not None or (
            len(recent) < self.policy.max_requests_per_window
            and (not recent or current - max(recent) >= self.policy.resend_cooldown)
        )
        self.store.record_request(email_hash, realm, current)
        identity = self.store.resolve_identity(normalized, realm) if normalized else None
        if not allowed or identity is None or identity.status != "ACTIVE":
            return OtpRequestResult(public_challenge_id, public_expiry)

        code = self.fixed_test_code or f"{secrets.randbelow(1_000_000):06d}"
        challenge = EmailOtpChallenge(
            challenge_id=public_challenge_id,
            identity_id=identity.identity_id,
            code_hash=_secret_hash(self.pepper, b"otp", code),
            attempts=0,
            expires_at=public_expiry,
        )
        self.store.create_challenge(challenge)
        if self.fixed_test_code is None:
            self.provider.send_sign_in_code(
                to_email=identity.normalized_email,
                code=code,
                expires_at=challenge.expires_at,
                realm=realm,
            )
            return OtpRequestResult(public_challenge_id, public_expiry)
        channel = "email" if "@" in normalized else "SMS"
        return OtpRequestResult(
            public_challenge_id,
            public_expiry,
            f"Fake {channel} sent. Use sign-in code {code}.",
        )

    def verify_code(
        self, challenge_id: UUID, code: str, *, now: datetime | None = None
    ) -> OtpSessionResult:
        current = now or datetime.now(UTC)
        challenge = self.store.get_challenge(challenge_id)
        if challenge is None:
            raise OtpAuthenticationError("invalid or expired sign-in code")
        identity = self.store.get_identity(challenge.identity_id)
        valid_state = (
            identity is not None
            and identity.status == "ACTIVE"
            and challenge.consumed_at is None
            and challenge.expires_at > current
            and challenge.attempts < self.policy.max_verification_attempts
        )
        expected_length = len(self.fixed_test_code) if self.fixed_test_code else 6
        valid_code = (
            len(code) == expected_length
            and code.isascii()
            and code.isdigit()
            and hmac.compare_digest(challenge.code_hash, _secret_hash(self.pepper, b"otp", code))
        )
        if not valid_state or not valid_code or identity is None:
            if challenge.attempts < self.policy.max_verification_attempts:
                self.store.record_failure(challenge_id, challenge.attempts + 1)
            raise OtpAuthenticationError("invalid or expired sign-in code")
        if not self.store.consume_challenge(challenge_id, current):
            raise OtpAuthenticationError("invalid or expired sign-in code")

        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = current + self.policy.session_ttl
        self.store.mark_identity_verified(identity.identity_id, current)
        self.store.create_session(
            identity=identity,
            session_token_hash=_secret_hash(self.pepper, b"session", session_token),
            csrf_token_hash=_secret_hash(self.pepper, b"csrf", csrf_token),
            expires_at=expires_at,
            created_at=current,
        )
        return OtpSessionResult(
            principal_id=identity.principal_id,
            account_id=identity.account_id,
            realm=identity.realm,
            session_token=session_token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
