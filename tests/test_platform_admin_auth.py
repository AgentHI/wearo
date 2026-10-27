from datetime import UTC, datetime, timedelta

from apps.api.wearo_api.platform_admin_auth import PlatformAdminAuth

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def test_only_configured_credentials_create_a_session() -> None:
    auth = PlatformAdminAuth("admin@wearo.ai", "correct-secret")

    assert auth.login("customer@example.com", "correct-secret", "client", now=NOW) is None
    assert auth.login("admin@wearo.ai", "wrong", "client", now=NOW) is None
    session = auth.login(" ADMIN@WEARO.AI ", "correct-secret", "client", now=NOW)

    assert session is not None
    assert auth.authenticate(session.token, now=NOW)


def test_repeated_failures_temporarily_lock_login() -> None:
    auth = PlatformAdminAuth(
        "admin@wearo.ai",
        "correct-secret",
        max_attempts=3,
        lockout=timedelta(minutes=10),
    )
    for _ in range(3):
        assert auth.login("admin@wearo.ai", "wrong", "client", now=NOW) is None

    assert auth.login("admin@wearo.ai", "correct-secret", "client", now=NOW) is None
    assert (
        auth.login(
            "admin@wearo.ai", "correct-secret", "client", now=NOW + timedelta(minutes=11)
        )
        is not None
    )


def test_session_expires_and_logout_invalidates_it() -> None:
    auth = PlatformAdminAuth(
        "admin@wearo.ai", "correct-secret", session_ttl=timedelta(minutes=20)
    )
    session = auth.login("admin@wearo.ai", "correct-secret", "client", now=NOW)
    assert session is not None
    assert not auth.authenticate(session.token, now=NOW + timedelta(minutes=20))

    second = auth.login("admin@wearo.ai", "correct-secret", "client", now=NOW)
    assert second is not None
    assert auth.invalidate(second.token)
    assert not auth.authenticate(second.token, now=NOW)


def test_logout_requires_matching_csrf_when_using_csrf_protected_operation() -> None:
    auth = PlatformAdminAuth("admin@wearo.ai", "correct-secret")
    session = auth.login("admin@wearo.ai", "correct-secret", "client", now=NOW)
    assert session is not None

    assert not auth.logout(session.token, "wrong-csrf")
    assert auth.authenticate(session.token, now=NOW)
    assert auth.logout(session.token, session.csrf_token)
    assert not auth.authenticate(session.token, now=NOW)
