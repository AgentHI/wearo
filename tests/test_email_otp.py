from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.email_otp import (
    AuthRealm,
    EmailOtpChallenge,
    EmailOtpPolicy,
    EmailOtpService,
    OtpAuthenticationError,
    OtpIdentity,
    normalize_email,
    normalize_test_destination,
)

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
PEPPER = b"wearo-test-otp-pepper-32-bytes!!"


class RecordingProvider:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, AuthRealm]] = []

    def send_sign_in_code(
        self, *, to_email: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None:
        self.messages.append((to_email, code, realm))


class MemoryOtpStore:
    def __init__(self, identity: OtpIdentity) -> None:
        self.identities = {identity.identity_id: identity}
        self.requests: list[tuple[bytes, AuthRealm, datetime]] = []
        self.challenges: dict[UUID, EmailOtpChallenge] = {}
        self.sessions: list[tuple[OtpIdentity, bytes, bytes]] = []

    def resolve_identity(self, normalized_email: str, realm: AuthRealm) -> OtpIdentity | None:
        return next(
            (
                i
                for i in self.identities.values()
                if i.normalized_email == normalized_email and i.realm == realm
            ),
            None,
        )

    def recent_request_times(
        self, email_hash: bytes, realm: AuthRealm, since: datetime
    ) -> tuple[datetime, ...]:
        return tuple(
            at
            for key, item_realm, at in self.requests
            if key == email_hash and item_realm == realm and at >= since
        )

    def record_request(self, email_hash: bytes, realm: AuthRealm, requested_at: datetime) -> None:
        self.requests.append((email_hash, realm, requested_at))

    def create_challenge(self, challenge: EmailOtpChallenge) -> None:
        self.challenges[challenge.challenge_id] = challenge

    def get_challenge(self, challenge_id: UUID) -> EmailOtpChallenge | None:
        return self.challenges.get(challenge_id)

    def get_identity(self, identity_id: UUID) -> OtpIdentity | None:
        return self.identities.get(identity_id)

    def record_failure(self, challenge_id: UUID, attempts: int) -> None:
        self.challenges[challenge_id] = replace(self.challenges[challenge_id], attempts=attempts)

    def consume_challenge(self, challenge_id: UUID, consumed_at: datetime) -> bool:
        challenge = self.challenges[challenge_id]
        if challenge.consumed_at is not None:
            return False
        self.challenges[challenge_id] = replace(challenge, consumed_at=consumed_at)
        return True

    def mark_identity_verified(self, identity_id: UUID, verified_at: datetime) -> None:
        return None

    def create_session(
        self,
        *,
        identity: OtpIdentity,
        session_token_hash: bytes,
        csrf_token_hash: bytes,
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        self.sessions.append((identity, session_token_hash, csrf_token_hash))


def make_service() -> tuple[EmailOtpService, MemoryOtpStore, RecordingProvider]:
    identity = OtpIdentity(uuid4(), uuid4(), uuid4(), "user@example.com", "SHOP", "ACTIVE")
    store = MemoryOtpStore(identity)
    provider = RecordingProvider()
    policy = EmailOtpPolicy(max_requests_per_window=3, max_verification_attempts=3)
    return EmailOtpService(store, provider, policy, pepper=PEPPER), store, provider


def request_valid_code(
    service: EmailOtpService, store: MemoryOtpStore, provider: RecordingProvider
) -> tuple[UUID, str]:
    service.request_code(" USER@Example.com ", "SHOP", now=NOW)
    challenge_id = next(iter(store.challenges))
    return challenge_id, provider.messages[0][1]


def test_normalization_and_generic_request_prevent_enumeration() -> None:
    service, store, provider = make_service()
    known = service.request_code(" USER@Example.com ", "SHOP", now=NOW)
    unknown = service.request_code("nobody@example.com", "SHOP", now=NOW)
    malformed = service.request_code("not-an-email", "SHOP", now=NOW)
    assert normalize_email(" USER@Example.com ") == "user@example.com"
    assert known.message == unknown.message == malformed.message
    assert len({known.challenge_id, unknown.challenge_id, malformed.challenge_id}) == 3
    assert known.expires_at == unknown.expires_at == malformed.expires_at
    assert len(provider.messages) == 1
    assert all(b"user@example.com" not in request[0] for request in store.requests)


def test_valid_code_creates_hashed_session_and_cannot_replay() -> None:
    service, store, provider = make_service()
    challenge_id, code = request_valid_code(service, store, provider)
    result = service.verify_code(challenge_id, code, now=NOW)
    assert result.realm == "SHOP"
    assert len(store.sessions) == 1
    assert result.session_token.encode() not in store.sessions[0][1]
    with pytest.raises(OtpAuthenticationError, match="invalid or expired"):
        service.verify_code(challenge_id, code, now=NOW)


def test_expiry_and_attempt_limit_fail_closed() -> None:
    service, store, provider = make_service()
    challenge_id, code = request_valid_code(service, store, provider)
    for _ in range(3):
        with pytest.raises(OtpAuthenticationError):
            service.verify_code(challenge_id, "000000", now=NOW)
    with pytest.raises(OtpAuthenticationError):
        service.verify_code(challenge_id, code, now=NOW)
    second_service, second_store, second_provider = make_service()
    second_id, second_code = request_valid_code(second_service, second_store, second_provider)
    with pytest.raises(OtpAuthenticationError):
        second_service.verify_code(second_id, second_code, now=NOW + timedelta(minutes=11))


def test_resend_cooldown_and_window_caps_do_not_send_or_disclose() -> None:
    service, _, provider = make_service()
    responses = [
        service.request_code("user@example.com", "SHOP", now=NOW + timedelta(seconds=i))
        for i in range(4)
    ]
    assert len(set(response.message for response in responses)) == 1
    assert len(provider.messages) == 1


def test_fixed_local_code_skips_delivery_but_keeps_one_time_session_flow() -> None:
    identity = OtpIdentity(uuid4(), uuid4(), uuid4(), "user@example.com", "SHOP", "ACTIVE")
    store = MemoryOtpStore(identity)
    provider = RecordingProvider()
    service = EmailOtpService(
        store,
        provider,
        EmailOtpPolicy(),
        pepper=PEPPER,
        fixed_test_code="1324",
    )

    challenge = service.request_code("user@example.com", "SHOP", now=NOW)
    result = service.verify_code(challenge.challenge_id, "1324", now=NOW)

    assert result.account_id == identity.account_id
    assert challenge.message == "Fake email sent. Use sign-in code 1324."
    assert provider.messages == []
    with pytest.raises(OtpAuthenticationError):
        service.verify_code(challenge.challenge_id, "1324", now=NOW)


def test_fixed_local_code_resend_always_returns_a_verifiable_challenge() -> None:
    identity = OtpIdentity(uuid4(), uuid4(), uuid4(), "+919876543210", "SHOP", "ACTIVE")
    store = MemoryOtpStore(identity)
    service = EmailOtpService(
        store,
        RecordingProvider(),
        EmailOtpPolicy(),
        pepper=PEPPER,
        fixed_test_code="1324",
    )

    service.request_code("+919876543210", "SHOP", now=NOW)
    latest = service.request_code("+919876543210", "SHOP", now=NOW + timedelta(seconds=1))

    assert latest.message == "Fake SMS sent. Use sign-in code 1324."
    assert service.verify_code(latest.challenge_id, "1324", now=NOW + timedelta(seconds=1))


def test_local_destination_normalization_accepts_email_or_mobile_only() -> None:
    assert normalize_test_destination(" Test@Example.COM ") == "test@example.com"
    assert normalize_test_destination("+91 (98765) 43210") == "+919876543210"
    assert normalize_test_destination("987-654-3210") == "9876543210"
    assert normalize_test_destination("not a destination") == ""
    with pytest.raises(ValueError, match="4 to 8 ASCII digits"):
        EmailOtpService(
            MemoryOtpStore(
                OtpIdentity(uuid4(), uuid4(), uuid4(), "user@example.com", "SHOP", "ACTIVE")
            ),
            RecordingProvider(),
            EmailOtpPolicy(),
            pepper=PEPPER,
            fixed_test_code="13AB",
        )
