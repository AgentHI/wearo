from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.admin_auth import (
    AdminAuthPolicy,
    AdminAuthService,
    AdminIdentity,
    AuthenticationError,
    MfaChallenge,
    hash_password,
    hash_secret,
    totp_code,
    verify_password,
)

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
MFA_SECRET = b"wearo-admin-totp-secret"


class PlaintextTestCipher:
    def decrypt(self, ciphertext: bytes) -> bytes:
        return ciphertext


class RecordingAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    def record(
        self, *, actor_id: UUID | None, action: str, target_id: UUID | None, occurred_at: datetime
    ) -> None:
        self.actions.append(action)


class MemoryAdminStore:
    def __init__(self, admin: AdminIdentity) -> None:
        self.admins = {admin.admin_id: admin}
        self.challenges: dict[UUID, MfaChallenge] = {}
        self.sessions: list[tuple[UUID, bytes, bytes, tuple[str, ...]]] = []
        self.recovery_hashes: dict[UUID, set[bytes]] = {admin.admin_id: set()}

    def find_admin(self, normalized_username: str) -> AdminIdentity | None:
        return next(
            (item for item in self.admins.values() if item.username == normalized_username), None
        )

    def get_admin(self, admin_id: UUID) -> AdminIdentity | None:
        return self.admins.get(admin_id)

    def record_password_failure(
        self, admin_id: UUID, *, failed_attempts: int, locked_until: datetime | None
    ) -> None:
        self.admins[admin_id] = replace(
            self.admins[admin_id], failed_attempts=failed_attempts, locked_until=locked_until
        )

    def record_password_success(self, admin_id: UUID, authenticated_at: datetime) -> None:
        self.admins[admin_id] = replace(self.admins[admin_id], failed_attempts=0, locked_until=None)

    def create_challenge(self, challenge: MfaChallenge, token_hash: bytes) -> None:
        self.challenges[challenge.challenge_id] = challenge

    def get_challenge(self, challenge_id: UUID) -> MfaChallenge | None:
        return self.challenges.get(challenge_id)

    def record_mfa_failure(self, challenge_id: UUID, attempts: int) -> None:
        self.challenges[challenge_id] = replace(self.challenges[challenge_id], attempts=attempts)

    def consume_challenge(self, challenge_id: UUID, consumed_at: datetime) -> bool:
        challenge = self.challenges[challenge_id]
        if challenge.consumed_at is not None:
            return False
        self.challenges[challenge_id] = replace(challenge, consumed_at=consumed_at)
        return True

    def create_session(
        self,
        *,
        admin_id: UUID,
        session_token_hash: bytes,
        csrf_token_hash: bytes,
        scopes: tuple[str, ...],
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        self.sessions.append((admin_id, session_token_hash, csrf_token_hash, scopes))

    def consume_recovery_code(self, admin_id: UUID, code_hash: bytes, used_at: datetime) -> bool:
        hashes = self.recovery_hashes[admin_id]
        if code_hash not in hashes:
            return False
        hashes.remove(code_hash)
        return True


def make_service() -> tuple[AdminAuthService, MemoryAdminStore, RecordingAudit, AdminIdentity]:
    admin = AdminIdentity(
        admin_id=uuid4(),
        username="admin@wearo.test",
        password_hash=hash_password("correct horse battery staple", salt=b"0123456789abcdef"),
        mfa_secret_encrypted=MFA_SECRET,
        scopes=("tenant:write", "audit:read"),
        status="ACTIVE",
        failed_attempts=0,
        locked_until=None,
    )
    store = MemoryAdminStore(admin)
    audit = RecordingAudit()
    policy = AdminAuthPolicy(
        max_password_attempts=3,
        password_lockout=timedelta(minutes=10),
        challenge_ttl=timedelta(minutes=5),
        max_mfa_attempts=3,
        session_ttl=timedelta(minutes=20),
        totp_window=0,
    )
    return AdminAuthService(store, PlaintextTestCipher(), audit, policy), store, audit, admin


def test_password_hash_round_trip_and_rejects_wrong_password() -> None:
    encoded = hash_password("secret", salt=b"0123456789abcdef")
    assert verify_password("secret", encoded)
    assert not verify_password("wrong", encoded)


def test_password_success_creates_only_mfa_challenge() -> None:
    service, store, audit, _ = make_service()
    challenge = service.begin_password_login(
        " ADMIN@WEARO.TEST ", "correct horse battery staple", now=NOW
    )
    assert challenge.challenge_id in store.challenges
    assert store.sessions == []
    assert audit.actions == ["admin.mfa_challenge_created"]


def test_valid_mfa_creates_scoped_admin_session_and_challenge_cannot_replay() -> None:
    service, store, audit, _ = make_service()
    challenge = service.begin_password_login(
        "admin@wearo.test", "correct horse battery staple", now=NOW
    )
    result = service.complete_mfa(challenge.challenge_id, totp_code(MFA_SECRET, NOW), now=NOW)
    assert result.scopes == ("tenant:write", "audit:read")
    assert len(store.sessions) == 1
    assert hash_secret(result.session_token) == store.sessions[0][1]
    assert "admin.session_created" in audit.actions
    with pytest.raises(AuthenticationError, match="invalid or expired"):
        service.complete_mfa(challenge.challenge_id, totp_code(MFA_SECRET, NOW), now=NOW)


def test_password_failures_lock_account_and_unknown_user_is_generic() -> None:
    service, store, _, admin = make_service()
    for _ in range(3):
        with pytest.raises(AuthenticationError, match="invalid administrator credentials"):
            service.begin_password_login("admin@wearo.test", "wrong", now=NOW)
    assert store.admins[admin.admin_id].locked_until == NOW + timedelta(minutes=10)
    with pytest.raises(AuthenticationError, match="invalid administrator credentials"):
        service.begin_password_login("consumer@wearo.test", "wrong", now=NOW)


def test_mfa_attempt_limit_and_expiry_fail_closed() -> None:
    service, store, _, _ = make_service()
    challenge = service.begin_password_login(
        "admin@wearo.test", "correct horse battery staple", now=NOW
    )
    for _ in range(3):
        with pytest.raises(AuthenticationError, match="invalid or expired"):
            service.complete_mfa(challenge.challenge_id, "000000", now=NOW)
    assert store.challenges[challenge.challenge_id].attempts == 3
    with pytest.raises(AuthenticationError, match="invalid or expired"):
        service.complete_mfa(challenge.challenge_id, totp_code(MFA_SECRET, NOW), now=NOW)


def test_recovery_code_is_single_use_and_still_requires_password_stage() -> None:
    service, store, audit, admin = make_service()
    store.recovery_hashes[admin.admin_id].add(hash_secret("one-time-recovery"))
    first = service.begin_password_login(
        "admin@wearo.test", "correct horse battery staple", now=NOW
    )
    result = service.complete_recovery(first.challenge_id, "one-time-recovery", now=NOW)
    assert result.admin_id == admin.admin_id
    assert "admin.recovery_code_used" in audit.actions
    second = service.begin_password_login(
        "admin@wearo.test", "correct horse battery staple", now=NOW
    )
    with pytest.raises(AuthenticationError, match="invalid or expired"):
        service.complete_recovery(second.challenge_id, "one-time-recovery", now=NOW)
