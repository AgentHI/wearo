from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.browser_sessions import (
    BrowserSession,
    BrowserSessionService,
    SessionAuthenticationError,
    SessionPolicy,
    session_cookie,
)

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)
PEPPER = b"wearo-test-session-pepper-32bytes"


class MemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[UUID, BrowserSession] = {}

    def find_by_token_hash(self, token_hash: bytes) -> BrowserSession | None:
        return next((s for s in self.sessions.values() if s.token_hash == token_hash), None)

    def replace_tokens(
        self,
        session_id: UUID,
        *,
        token_hash: bytes,
        csrf_hash: bytes,
        expires_at: datetime,
        rotated_at: datetime,
    ) -> bool:
        session = self.sessions.get(session_id)
        if session is None or session.revoked_at is not None:
            return False
        self.sessions[session_id] = replace(
            session,
            token_hash=token_hash,
            csrf_hash=csrf_hash,
            created_at=rotated_at,
            expires_at=expires_at,
        )
        return True

    def revoke(self, session_id: UUID, revoked_at: datetime) -> bool:
        session = self.sessions.get(session_id)
        if session is None or session.revoked_at is not None:
            return False
        self.sessions[session_id] = replace(session, revoked_at=revoked_at)
        return True

    def revoke_principal(self, principal_id: UUID, revoked_at: datetime) -> int:
        ids = [
            key
            for key, session in self.sessions.items()
            if session.principal_id == principal_id and session.revoked_at is None
        ]
        for key in ids:
            self.sessions[key] = replace(self.sessions[key], revoked_at=revoked_at)
        return len(ids)


def make_service() -> tuple[BrowserSessionService, MemoryStore, str, str, BrowserSession]:
    store = MemoryStore()
    service = BrowserSessionService(store, SessionPolicy(), pepper=PEPPER)
    token, csrf = "session-secret", "csrf-secret"
    session = BrowserSession(
        uuid4(),
        uuid4(),
        uuid4(),
        "SHOP",
        service._hash(b"session", token),
        service._hash(b"csrf", csrf),
        NOW - timedelta(days=2),
        NOW + timedelta(days=2),
        None,
    )
    store.sessions[session.session_id] = session
    return service, store, token, csrf, session


def test_read_and_mutation_require_correct_realm_and_csrf() -> None:
    service, _, token, csrf, session = make_service()
    assert service.authenticate(token, expected_realm="SHOP", now=NOW) == session
    assert (
        service.authenticate(token, expected_realm="SHOP", csrf_token=csrf, mutation=True, now=NOW)
        == session
    )
    for kwargs in (
        {"expected_realm": "BUSINESS"},
        {"expected_realm": "SHOP", "csrf_token": "wrong", "mutation": True},
    ):
        with pytest.raises(SessionAuthenticationError):
            service.authenticate(token, now=NOW, **kwargs)


def test_rotation_invalidates_old_token() -> None:
    service, _, token, _, _ = make_service()
    credentials = service.rotate(token, now=NOW)
    with pytest.raises(SessionAuthenticationError):
        service.authenticate(token, expected_realm="SHOP", now=NOW)
    assert service.authenticate(credentials.session_token, expected_realm="SHOP", now=NOW)


def test_logout_and_principal_revocation_fail_closed() -> None:
    service, store, token, csrf, session = make_service()
    service.logout(token, csrf, now=NOW)
    with pytest.raises(SessionAuthenticationError):
        service.authenticate(token, expected_realm="SHOP", now=NOW)
    assert service.revoke_all(session.principal_id, now=NOW) == 0
    assert store.sessions[session.session_id].revoked_at == NOW


def test_cookie_has_required_browser_security_flags() -> None:
    cookie = session_cookie("secret", 3600)
    for value in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=3600"):
        assert value in cookie
