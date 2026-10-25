from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from apps.api.wearo_api.account_lifecycle import (
    DELETION_GRACE_PERIOD,
    AccountLifecycle,
    AccountLifecycleError,
    PostgresAccountLifecycle,
    deletion_eligibility,
)
from apps.api.wearo_api.beta_profile import ProfileError
from apps.api.wearo_api.browser_sessions import BrowserSession, SessionAuthenticationError
from apps.api.wearo_api.email_otp import OtpSessionResult
from apps.api.wearo_api.http_api import ApiContainer, create_app
from apps.api.wearo_api.media_runtime import FilesystemPrivateBlobStore


class NullBlobStore:
    def delete_asset_family(self, key: str) -> None:
        raise AssertionError(f"restoration must not delete {key}")

    def delete_render_preview(self, job_id: UUID) -> None:
        raise AssertionError(f"restoration must not delete preview {job_id}")


class FakeResult:
    def __init__(
        self,
        row: dict[str, Any] | None = None,
        scalar_values: tuple[object, ...] = (),
    ) -> None:
        self.row = row
        self.scalar_values = scalar_values

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def scalars(self) -> tuple[object, ...]:
        return self.scalar_values


class FakeConnection:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, statement: object, parameters: dict[str, object] | None = None) -> FakeResult:
        sql = str(statement)
        values = parameters or {}
        self.calls.append((sql, values))
        if "SELECT a.status, a.cancellation_at" in sql:
            return FakeResult(self.row)
        if "SELECT a.status, a.deletion_at" in sql:
            return FakeResult(self.row)
        if "UPDATE accounts" in sql:
            if "SET status = 'DELETION_PENDING'" in sql:
                self.row.update(
                    status="DELETION_PENDING",
                    cancellation_at=values["cancelled_at"],
                    deletion_at=values["delete_at"],
                    permanently_deleted_at=None,
                    deletion_outcome=None,
                )
            elif "SET status = 'ACTIVE'" in sql:
                self.row.update(
                    status="ACTIVE",
                    cancellation_at=None,
                    deletion_at=None,
                    permanently_deleted_at=None,
                )
        if "SELECT account_id FROM accounts" in sql:
            return FakeResult(scalar_values=())
        return FakeResult()


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> FakeConnection:
        return self.connection

    def __exit__(self, *args: object) -> None:
        return None


class FakeEngine:
    def __init__(self, row: dict[str, Any]) -> None:
        self.connection = FakeConnection(row)

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class ProcessorConnection:
    def __init__(
        self,
        accounts: dict[UUID, dict[str, Any]],
        restore_before_recheck: UUID | None = None,
        fail_once_on: str | None = None,
    ) -> None:
        self.accounts = accounts
        self.restore_before_recheck = restore_before_recheck
        self.fail_once_on = fail_once_on
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, statement: object, parameters: dict[str, object] | None = None) -> FakeResult:
        sql = str(statement)
        values = parameters or {}
        self.calls.append((sql, values))
        if self.fail_once_on is not None and self.fail_once_on in sql:
            self.fail_once_on = None
            raise SQLAlchemyError("temporary database failure")
        if "SELECT account_id FROM accounts" in sql:
            now = cast(datetime, values["now"])
            limit = cast(int, values["limit"])
            eligible = sorted(
                (
                    (cast(datetime, row["deletion_at"]), account_id)
                    for account_id, row in self.accounts.items()
                    if row["status"] == "DELETION_PENDING"
                    and row["deletion_at"] is not None
                    and cast(datetime, row["deletion_at"]) <= now
                ),
                key=lambda item: (item[0], item[1]),
            )
            return FakeResult(scalar_values=tuple(account_id for _, account_id in eligible[:limit]))
        account_id = cast(UUID | None, values.get("account"))
        if "SELECT object_key FROM media_assets" in sql and account_id is not None:
            media = cast(tuple[str, ...], self.accounts[account_id]["media"])
            return FakeResult(scalar_values=media)
        if "SELECT job_id FROM render_jobs" in sql and account_id is not None:
            jobs = cast(tuple[UUID, ...], self.accounts[account_id]["jobs"])
            return FakeResult(scalar_values=jobs)
        if "SELECT status, deletion_at FROM accounts" in sql and account_id is not None:
            if account_id == self.restore_before_recheck:
                self.accounts[account_id]["status"] = "ACTIVE"
                self.accounts[account_id]["deletion_at"] = None
                self.restore_before_recheck = None
            return FakeResult(self.accounts[account_id])
        if "SET status = 'PERMANENTLY_DELETED'" in sql and account_id is not None:
            self.accounts[account_id]["status"] = "PERMANENTLY_DELETED"
            self.accounts[account_id]["permanently_deleted_at"] = values["now"]
            self.accounts[account_id]["deletion_outcome"] = "COMPLETED"
        return FakeResult()


class ProcessorEngine:
    def __init__(
        self,
        accounts: dict[UUID, dict[str, Any]],
        restore_before_recheck: UUID | None = None,
        fail_once_on: str | None = None,
    ) -> None:
        self.connection = ProcessorConnection(accounts, restore_before_recheck, fail_once_on)

    def begin(self) -> FakeTransaction:
        return FakeTransaction(cast(FakeConnection, self.connection))


class RecordingBlobStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_asset_family(self, key: str) -> None:
        self.deleted.append(key)

    def delete_render_preview(self, job_id: UUID) -> None:
        self.deleted.append(f"private/previews/{job_id.hex}")


class RetryableBlobStore:
    def __init__(self, original_key: str) -> None:
        self.original_key = original_key
        self.items = {
            original_key,
            f"{original_key}.thumbnail.webp",
            f"{original_key}.optimized.webp",
            f"{original_key}.generated-copy.png",
        }
        self.fail_once = True

    def delete_asset_family(self, key: str) -> None:
        self.items.discard(key)
        if self.fail_once:
            self.fail_once = False
            raise OSError("temporary storage failure")
        self.items = {item for item in self.items if not item.startswith(f"{key}.")}

    def delete_render_preview(self, job_id: UUID) -> None:
        return None


class RetryablePreviewBlobStore:
    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        self.preview_exists = True
        self.fail_once = True
        self.profile_deletions = 0

    def delete_asset_family(self, key: str) -> None:
        self.profile_deletions += 1

    def delete_render_preview(self, job_id: UUID) -> None:
        assert job_id == self.job_id
        if self.fail_once:
            self.fail_once = False
            raise TimeoutError("temporary preview deletion timeout")
        self.preview_exists = False


class FixedTimeLifecycle(PostgresAccountLifecycle):
    def __init__(self, engine: Engine, recovery_time: datetime) -> None:
        super().__init__(engine, NullBlobStore())
        self.recovery_time = recovery_time

    def restore(
        self, account_id: UUID, principal_id: UUID, *, now: datetime | None = None
    ) -> datetime:
        return super().restore(account_id, principal_id, now=self.recovery_time)


class StaticPendingOtp:
    def __init__(self, result: OtpSessionResult) -> None:
        self.result = result

    def verify_code(self, challenge_id: UUID, code: str) -> OtpSessionResult:
        return self.result


class MissingProfiles:
    def restore_requested(self, account_id: UUID) -> bool:
        return False

    def require(self, account_id: UUID) -> None:
        raise ProfileError("profile not created")


class RecoverableProfiles:
    def __init__(self) -> None:
        self.restored_account_id: UUID | None = None
        self.active = False

    def restore_requested(self, account_id: UUID) -> bool:
        self.restored_account_id = account_id
        self.active = True
        return True

    def require(self, account_id: UUID) -> None:
        if not self.active or account_id != self.restored_account_id:
            raise ProfileError("profile not created")


class StrictConsumerSessions:
    session_value = "user-a-session"
    csrf = "user-a-csrf"

    def __init__(self, account_id: UUID, principal_id: UUID) -> None:
        now = datetime.now(UTC)
        self.session = BrowserSession(
            uuid4(),
            account_id,
            principal_id,
            "SHOP",
            b"token-hash",
            b"csrf-hash",
            now,
            now + timedelta(hours=1),
            None,
        )

    def authenticate(
        self,
        token: str,
        *,
        expected_realm: str,
        csrf_token: str | None = None,
        mutation: bool = False,
        **_: object,
    ) -> BrowserSession:
        if (
            token != self.session_value
            or expected_realm != "SHOP"
            or (mutation and csrf_token != self.csrf)
        ):
            raise SessionAuthenticationError("invalid session")
        return self.session


class RecordingLifecycle:
    def __init__(self, account_id: UUID) -> None:
        self.account_id = account_id
        self.calls: list[tuple[UUID, UUID]] = []

    def cancel(self, account_id: UUID, principal_id: UUID) -> AccountLifecycle:
        self.calls.append((account_id, principal_id))
        cancelled_at = datetime(2026, 10, 25, 12, tzinfo=UTC)
        return AccountLifecycle(
            account_id,
            "DELETION_PENDING",
            cancelled_at,
            deletion_eligibility(cancelled_at),
        )


class FailIfCalledOtp:
    def __init__(self) -> None:
        self.called = False

    def verify_code(self, challenge_id: UUID, code: str) -> OtpSessionResult:
        self.called = True
        raise AssertionError("invalid restoration payload must not reach OTP verification")


def lifecycle_api_container(
    account_id: UUID,
    principal_id: UUID,
    lifecycle: RecordingLifecycle,
) -> ApiContainer:
    unavailable = cast(Any, None)
    return ApiContainer(
        engine=unavailable,
        otp=unavailable,
        sessions=cast(Any, StrictConsumerSessions(account_id, principal_id)),
        media=unavailable,
        consents=unavailable,
        profiles=unavailable,
        quota=unavailable,
        renders=unavailable,
        account_lifecycle=cast(Any, lifecycle),
        secure_cookie=False,
    )


def test_deletion_eligibility_is_exactly_thirty_days_after_cancellation() -> None:
    cancelled_at = datetime(2026, 10, 25, 14, 30, 45, 123456, tzinfo=UTC)

    assert DELETION_GRACE_PERIOD == timedelta(days=30)
    assert deletion_eligibility(cancelled_at) == datetime(
        2026, 11, 24, 14, 30, 45, 123456, tzinfo=UTC
    )


def test_deletion_eligibility_rejects_ambiguous_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        deletion_eligibility(datetime(2026, 10, 25, 14, 30))


def test_cancellation_derives_account_and_principal_from_authenticated_session() -> None:
    account_id, principal_id = uuid4(), uuid4()
    lifecycle = RecordingLifecycle(account_id)
    container = lifecycle_api_container(account_id, principal_id, lifecycle)

    with TestClient(create_app(container)) as client:
        client.cookies.set("wearo_consumer_session", StrictConsumerSessions.session_value)
        response = client.delete(
            "/api/v1/me/account",
            headers={"X-CSRF-Token": StrictConsumerSessions.csrf},
        )

    assert response.status_code == 202
    assert response.json()["account_id"] == str(account_id)
    assert lifecycle.calls == [(account_id, principal_id)]


@pytest.mark.parametrize(
    "request_arguments",
    [
        {"json": {"account_id": str(uuid4())}},
        {"json": {"tenant_id": str(uuid4()), "deletion_at": "2099-01-01T00:00:00Z"}},
        {"params": {"account_id": str(uuid4()), "deletion_at": "2099-01-01T00:00:00Z"}},
    ],
    ids=["another-user", "tenant-and-deadline-body", "identity-and-deadline-query"],
)
def test_cancellation_rejects_frontend_owned_identity_and_deadline_fields(
    request_arguments: dict[str, Any],
) -> None:
    account_id, principal_id = uuid4(), uuid4()
    lifecycle = RecordingLifecycle(account_id)
    container = lifecycle_api_container(account_id, principal_id, lifecycle)

    with TestClient(create_app(container)) as client:
        client.cookies.set("wearo_consumer_session", StrictConsumerSessions.session_value)
        response = client.request(
            "DELETE",
            "/api/v1/me/account",
            headers={"X-CSRF-Token": StrictConsumerSessions.csrf},
            **request_arguments,
        )

    assert response.status_code == 422
    assert response.json()["code"] == "ACCOUNT_LIFECYCLE_FIELDS_SERVER_MANAGED"
    assert lifecycle.calls == []


@pytest.mark.parametrize(
    "cookie",
    [
        None,
        ("wearo_business_session", "unrelated-business-staff-session"),
        ("wearo_agent_session", "unrelated-agent-session"),
    ],
    ids=["unauthenticated", "business-staff", "business-agent"],
)
def test_cancellation_rejects_unauthenticated_and_b2b_staff_callers(
    cookie: tuple[str, str] | None,
) -> None:
    account_id, principal_id = uuid4(), uuid4()
    lifecycle = RecordingLifecycle(account_id)
    container = lifecycle_api_container(account_id, principal_id, lifecycle)

    with TestClient(create_app(container)) as client:
        if cookie is not None:
            client.cookies.set(*cookie)
        response = client.delete(
            "/api/v1/me/account",
            headers={"X-CSRF-Token": StrictConsumerSessions.csrf},
        )

    assert response.status_code == 401
    assert lifecycle.calls == []


def test_restoration_rejects_frontend_owned_account_and_deletion_fields() -> None:
    otp = FailIfCalledOtp()
    unavailable = cast(Any, None)
    container = ApiContainer(
        engine=unavailable,
        otp=cast(Any, otp),
        sessions=unavailable,
        media=unavailable,
        consents=unavailable,
        profiles=unavailable,
        quota=unavailable,
        renders=unavailable,
        account_lifecycle=unavailable,
        secure_cookie=False,
    )

    with TestClient(create_app(container)) as client:
        response = client.post(
            "/api/v1/auth/email-otp/verify",
            json={
                "challenge_id": str(uuid4()),
                "code": "123456",
                "account_id": str(uuid4()),
                "tenant_id": str(uuid4()),
                "deletion_at": "2099-01-01T00:00:00Z",
            },
        )

    assert response.status_code == 422
    assert otp.called is False


def test_permanent_deletion_has_no_public_or_staff_api_route() -> None:
    account_id, principal_id, unrelated_customer_id = uuid4(), uuid4(), uuid4()
    lifecycle = RecordingLifecycle(account_id)
    app = create_app(lifecycle_api_container(account_id, principal_id, lifecycle))
    exposed_paths = {getattr(route, "path", "") for route in app.routes}

    assert not any(
        "permanent" in path or "purge" in path or "deletion-worker" in path
        for path in exposed_paths
    )
    with TestClient(app) as client:
        client.cookies.set("wearo_agent_session", "unrelated-agent-session")
        response = client.delete(f"/api/v1/accounts/{unrelated_customer_id}/permanent-deletion")

    assert response.status_code == 404
    assert lifecycle.calls == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), "TIMEOUT"),
        (ConnectionError(), "SERVICE_UNAVAILABLE"),
        (OSError(), "STORAGE_FAILURE"),
        (SQLAlchemyError(), "DATABASE_FAILURE"),
        (RuntimeError(), "UNEXPECTED_FAILURE"),
    ],
)
def test_deletion_failures_are_recorded_as_non_sensitive_categories(
    error: Exception, expected: str
) -> None:
    assert PostgresAccountLifecycle._failure_code(error) == expected


def test_scenario_a_cancel_and_never_return_permanently_removes_account_data(
    tmp_path: Path,
) -> None:
    account_id, principal_id, preview_id = uuid4(), uuid4(), uuid4()
    cancelled_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    account_engine = FakeEngine(
        {
            "status": "ACTIVE",
            "principal_status": "ACTIVE",
            "cancellation_at": None,
            "deletion_at": None,
            "permanently_deleted_at": None,
            "deletion_outcome": None,
        }
    )
    blobs = FilesystemPrivateBlobStore(tmp_path)
    profile_key = f"private/{account_id}/profile"
    tryon_key = f"private/{account_id}/try-on"
    preview_key = f"private/previews/{preview_id.hex}"
    stored_keys = (
        profile_key,
        f"{profile_key}.thumbnail.webp",
        tryon_key,
        f"{tryon_key}.optimized.webp",
        preview_key,
        f"{preview_key}.generated-copy.png",
    )
    for key in stored_keys:
        blobs.put(key, b"private image")

    lifecycle = PostgresAccountLifecycle(cast(Engine, account_engine), blobs)
    pending = lifecycle.cancel(account_id, principal_id, now=cancelled_at)

    assert pending.status == "DELETION_PENDING"
    assert pending.deletion_at is not None
    assert pending.deletion_at == cancelled_at + timedelta(days=30)
    assert all(blobs.get(key) is not None for key in stored_keys)
    cancellation_sql = "\n".join(sql for sql, _ in account_engine.connection.calls)
    assert "UPDATE plan_assignments" in cancellation_sql
    assert "UPDATE offering_entitlements" in cancellation_sql

    processor_engine = ProcessorEngine(
        {
            account_id: {
                "status": "DELETION_PENDING",
                "deletion_at": pending.deletion_at,
                "media": (profile_key, tryon_key),
                "jobs": (preview_id,),
            }
        }
    )
    processor = PostgresAccountLifecycle(cast(Engine, processor_engine), blobs)
    assert processor.purge_due(now=pending.deletion_at - timedelta(microseconds=1)) == ()
    assert all(blobs.get(key) is not None for key in stored_keys)

    assert processor.purge_due(now=pending.deletion_at) == (account_id,)
    assert processor_engine.connection.accounts[account_id]["status"] == "PERMANENTLY_DELETED"
    assert all(blobs.get(key) is None for key in stored_keys)
    cleanup_sql = "\n".join(sql for sql, _ in processor_engine.connection.calls)
    assert "DELETE FROM person_profile_images" in cleanup_sql
    assert "SET normalized_value = 'deleted-'" in cleanup_sql
    assert "consumer_account_id = NULL" in cleanup_sql

    deleted_engine = FakeEngine(
        {
            "status": "PERMANENTLY_DELETED",
            "deletion_at": pending.deletion_at,
            "permanently_deleted_at": pending.deletion_at,
        }
    )
    with pytest.raises(AccountLifecycleError, match="restoration is unavailable"):
        PostgresAccountLifecycle(cast(Engine, deleted_engine), blobs).restore(
            account_id, principal_id, now=pending.deletion_at + timedelta(seconds=1)
        )


def test_scenario_b_cancel_and_return_restores_data_but_not_subscription(tmp_path: Path) -> None:
    account_id, principal_id = uuid4(), uuid4()
    cancelled_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    restored_at = cancelled_at + timedelta(days=29)
    engine = FakeEngine(
        {
            "status": "ACTIVE",
            "principal_status": "ACTIVE",
            "cancellation_at": None,
            "deletion_at": None,
            "permanently_deleted_at": None,
            "deletion_outcome": None,
        }
    )
    blobs = FilesystemPrivateBlobStore(tmp_path)
    profile_key = f"private/{account_id}/profile"
    tryon_key = f"private/{account_id}/try-on"
    blobs.put(profile_key, b"profile")
    blobs.put(tryon_key, b"try-on")
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), blobs)

    pending = lifecycle.cancel(account_id, principal_id, now=cancelled_at)
    assert pending.deletion_at is not None
    billing_updates_after_cancel = sum(
        "UPDATE plan_assignments" in sql or "UPDATE offering_entitlements" in sql
        for sql, _ in engine.connection.calls
    )
    assert lifecycle.restore(account_id, principal_id, now=restored_at) == pending.deletion_at

    assert engine.connection.row["status"] == "ACTIVE"
    assert engine.connection.row["cancellation_at"] is None
    assert engine.connection.row["deletion_at"] is None
    assert blobs.get(profile_key) == b"profile"
    assert blobs.get(tryon_key) == b"try-on"
    assert (
        sum(
            "UPDATE plan_assignments" in sql or "UPDATE offering_entitlements" in sql
            for sql, _ in engine.connection.calls
        )
        == billing_updates_after_cancel
    )

    restored_processor_engine = ProcessorEngine(
        {
            account_id: {
                "status": "ACTIVE",
                "deletion_at": None,
                "media": (profile_key, tryon_key),
                "jobs": (),
            }
        }
    )
    restored_processor = PostgresAccountLifecycle(cast(Engine, restored_processor_engine), blobs)
    assert restored_processor.purge_due(now=pending.deletion_at + timedelta(days=1)) == ()
    assert blobs.get(profile_key) == b"profile"
    assert blobs.get(tryon_key) == b"try-on"


def test_scenario_c_second_cancellation_starts_a_new_thirty_day_window() -> None:
    account_id, principal_id = uuid4(), uuid4()
    first_cancelled_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    restored_at = first_cancelled_at + timedelta(days=15)
    second_cancelled_at = restored_at + timedelta(days=5)
    engine = FakeEngine(
        {
            "status": "ACTIVE",
            "principal_status": "ACTIVE",
            "cancellation_at": None,
            "deletion_at": None,
            "permanently_deleted_at": None,
            "deletion_outcome": None,
        }
    )
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), NullBlobStore())

    first = lifecycle.cancel(account_id, principal_id, now=first_cancelled_at)
    lifecycle.restore(account_id, principal_id, now=restored_at)
    second = lifecycle.cancel(account_id, principal_id, now=second_cancelled_at)

    assert first.deletion_at == first_cancelled_at + timedelta(days=30)
    assert second.cancellation_at == second_cancelled_at
    assert second.deletion_at == second_cancelled_at + timedelta(days=30)
    assert second.deletion_at != first.deletion_at
    assert engine.connection.row["cancellation_at"] == second_cancelled_at
    assert engine.connection.row["deletion_at"] == second.deletion_at


def test_full_lifecycle_audit_events_are_emitted_in_order_without_personal_data() -> None:
    account_id, principal_id = uuid4(), uuid4()
    first_cancellation = datetime(2026, 10, 1, 12, tzinfo=UTC)
    restored_at = first_cancellation + timedelta(days=1)
    final_cancellation = restored_at + timedelta(days=1)
    deletion_at = deletion_eligibility(final_cancellation)
    account_engine = FakeEngine(
        {
            "status": "ACTIVE",
            "principal_status": "ACTIVE",
            "cancellation_at": None,
            "deletion_at": None,
            "permanently_deleted_at": None,
            "deletion_outcome": None,
        }
    )
    lifecycle = PostgresAccountLifecycle(cast(Engine, account_engine), NullBlobStore())

    lifecycle.cancel(account_id, principal_id, now=first_cancellation)
    lifecycle.restore(account_id, principal_id, now=restored_at)
    lifecycle.cancel(account_id, principal_id, now=final_cancellation)

    processor_engine = ProcessorEngine(
        {
            account_id: {
                "status": "DELETION_PENDING",
                "deletion_at": deletion_at,
                "media": (),
                "jobs": (),
            }
        }
    )
    processor = PostgresAccountLifecycle(cast(Engine, processor_engine), RecordingBlobStore())
    assert processor.purge_due(now=deletion_at) == (account_id,)

    event_names = (
        "SUBSCRIPTION_CANCELLATION_REQUESTED",
        "SUBSCRIPTION_CANCELLED",
        "ACCOUNT_MARKED_FOR_DELETION",
        "ACCOUNT_RESTORED",
        "PERMANENT_DELETION_STARTED",
        "PERMANENT_DELETION_COMPLETED",
        "PERMANENT_DELETION_FAILED",
    )
    statements = account_engine.connection.calls + processor_engine.connection.calls
    events = []
    audit_sql = []
    for sql, _ in statements:
        if "INSERT INTO audit_events" not in sql or "WITH interrupted" in sql:
            continue
        audit_sql.append(sql)
        matches = [(sql.index(name), name) for name in event_names if name in sql]
        events.append(min(matches)[1])

    assert events == [
        "SUBSCRIPTION_CANCELLATION_REQUESTED",
        "SUBSCRIPTION_CANCELLED",
        "ACCOUNT_MARKED_FOR_DELETION",
        "ACCOUNT_RESTORED",
        "SUBSCRIPTION_CANCELLATION_REQUESTED",
        "SUBSCRIPTION_CANCELLED",
        "ACCOUNT_MARKED_FOR_DELETION",
        "PERMANENT_DELETION_STARTED",
        "PERMANENT_DELETION_COMPLETED",
    ]
    assert all("source_application" in sql and "outcome" in sql for sql in audit_sql)
    assert any("business_participants" in sql and "'B2B2C'" in sql for sql in audit_sql)
    assert all("normalized_value" not in sql and "mobile" not in sql for sql in audit_sql)


@pytest.mark.parametrize(
    "elapsed",
    [
        timedelta(days=1),
        timedelta(days=15),
        timedelta(days=29),
        DELETION_GRACE_PERIOD - timedelta(microseconds=1),
    ],
    ids=["day-1", "day-15", "day-29", "just-before-deadline"],
)
def test_login_during_recovery_period_restores_existing_account(elapsed: timedelta) -> None:
    account_id, principal_id = uuid4(), uuid4()
    cancelled_at = datetime(2026, 10, 25, 9, 15, tzinfo=UTC)
    deletion_at = deletion_eligibility(cancelled_at)
    recovery_time = cancelled_at + elapsed
    engine = FakeEngine(
        {
            "status": "DELETION_PENDING",
            "cancellation_at": cancelled_at,
            "deletion_at": deletion_at,
        }
    )
    lifecycle = FixedTimeLifecycle(cast(Engine, engine), recovery_time)
    otp = StaticPendingOtp(
        OtpSessionResult(
            principal_id=principal_id,
            account_id=account_id,
            realm="SHOP",
            session_token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=deletion_at + timedelta(days=1),
            account_status="DELETION_PENDING",
        )
    )
    unavailable = cast(Any, None)
    container = ApiContainer(
        engine=unavailable,
        otp=cast(Any, otp),
        sessions=unavailable,
        media=unavailable,
        consents=unavailable,
        profiles=cast(Any, MissingProfiles()),
        quota=unavailable,
        renders=unavailable,
        account_lifecycle=lifecycle,
        secure_cookie=False,
    )

    with TestClient(create_app(container)) as client:
        response = client.post(
            "/api/v1/auth/email-otp/verify",
            json={"challenge_id": str(uuid4()), "code": "123456"},
        )

    assert response.status_code == 200
    assert response.json()["account_id"] == str(account_id)
    assert datetime.fromisoformat(response.json()["restored_from_deletion_at"]) == deletion_at
    account_updates = [call for call in engine.connection.calls if "UPDATE accounts" in call[0]]
    assert len(account_updates) == 1
    update_sql, update_parameters = account_updates[0]
    assert "SET status = 'ACTIVE'" in update_sql
    assert "cancellation_at = NULL" in update_sql
    assert "deletion_at = NULL" in update_sql
    assert update_parameters["account"] == account_id
    assert update_parameters["now"] == recovery_time
    assert all("INSERT INTO accounts" not in sql for sql, _ in engine.connection.calls)
    assert engine.connection.row["status"] == "ACTIVE"
    assert engine.connection.row["cancellation_at"] is None
    assert engine.connection.row["deletion_at"] is None

    audit_inserts = [call for call in engine.connection.calls if "ACCOUNT_RESTORED" in call[0]]
    assert len(audit_inserts) == 1
    assert audit_inserts[0][1]["account"] == account_id
    assert audit_inserts[0][1]["principal"] == principal_id
    assert audit_inserts[0][1]["deletion_at"] == deletion_at

    assert lifecycle.purge_due(now=deletion_at + timedelta(days=1)) == ()
    preserved_mutations = (
        "UPDATE media_assets",
        "DELETE FROM media_assets",
        "UPDATE person_profiles",
        "DELETE FROM person_profiles",
        "UPDATE render_results",
        "DELETE FROM render_results",
        "UPDATE render_jobs",
        "DELETE FROM render_jobs",
    )
    assert all(
        not any(fragment in sql for fragment in preserved_mutations)
        for sql, _ in engine.connection.calls
    )
    assert all("UPDATE plan_assignments" not in sql for sql, _ in engine.connection.calls)


def test_login_restores_legacy_profile_deletion_request_before_storage_purge() -> None:
    account_id, principal_id = uuid4(), uuid4()
    profiles = RecoverableProfiles()
    otp = StaticPendingOtp(
        OtpSessionResult(
            principal_id=principal_id,
            account_id=account_id,
            realm="SHOP",
            session_token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            account_status="ACTIVE",
        )
    )
    unavailable = cast(Any, None)
    container = ApiContainer(
        engine=unavailable,
        otp=cast(Any, otp),
        sessions=unavailable,
        media=unavailable,
        consents=unavailable,
        profiles=cast(Any, profiles),
        quota=unavailable,
        renders=unavailable,
        secure_cookie=False,
    )

    with TestClient(create_app(container)) as client:
        response = client.post(
            "/api/v1/auth/email-otp/verify",
            json={"challenge_id": str(uuid4()), "code": "123456"},
        )

    assert response.status_code == 200
    assert response.json()["has_person_profile"] is True
    assert profiles.restored_account_id == account_id


def test_login_at_deletion_deadline_cannot_restore_account() -> None:
    account_id, principal_id = uuid4(), uuid4()
    cancelled_at = datetime(2026, 10, 25, 9, 15, tzinfo=UTC)
    deletion_at = deletion_eligibility(cancelled_at)
    engine = FakeEngine({"status": "DELETION_PENDING", "deletion_at": deletion_at})
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), NullBlobStore())

    with pytest.raises(AccountLifecycleError) as error:
        lifecycle.restore(account_id, principal_id, now=deletion_at)

    assert error.value.code == "ACCOUNT_RESTORATION_UNAVAILABLE"
    assert all("UPDATE accounts" not in sql for sql, _ in engine.connection.calls)
    assert all("ACCOUNT_RESTORED" not in sql for sql, _ in engine.connection.calls)


def test_permanently_deleted_account_cannot_be_restored() -> None:
    account_id, principal_id = uuid4(), uuid4()
    deletion_at = datetime(2026, 11, 24, 9, 15, tzinfo=UTC)
    engine = FakeEngine(
        {
            "status": "PERMANENTLY_DELETED",
            "deletion_at": deletion_at,
            "permanently_deleted_at": deletion_at + timedelta(seconds=1),
        }
    )
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), NullBlobStore())

    with pytest.raises(AccountLifecycleError) as error:
        lifecycle.restore(account_id, principal_id, now=deletion_at + timedelta(days=1))

    assert error.value.code == "ACCOUNT_RESTORATION_UNAVAILABLE"
    assert all("UPDATE accounts" not in sql for sql, _ in engine.connection.calls)
    assert all("ACCOUNT_RESTORED" not in sql for sql, _ in engine.connection.calls)


def test_scheduled_deletion_processor_selects_only_expired_pending_accounts() -> None:
    now = datetime(2026, 12, 1, 12, tzinfo=UTC)
    expired_id, future_id, active_old_id, restored_id = uuid4(), uuid4(), uuid4(), uuid4()
    preview_id = uuid4()
    accounts: dict[UUID, dict[str, Any]] = {
        expired_id: {
            "status": "DELETION_PENDING",
            "deletion_at": now - timedelta(seconds=1),
            "media": (f"private/{expired_id}/profile", f"private/{expired_id}/try-on"),
            "jobs": (preview_id,),
        },
        future_id: {
            "status": "DELETION_PENDING",
            "deletion_at": now + timedelta(seconds=1),
            "media": (f"private/{future_id}/profile",),
            "jobs": (),
        },
        active_old_id: {
            "status": "ACTIVE",
            "deletion_at": now - timedelta(days=90),
            "media": (f"private/{active_old_id}/profile",),
            "jobs": (),
        },
        restored_id: {
            "status": "ACTIVE",
            "deletion_at": None,
            "media": (f"private/{restored_id}/profile",),
            "jobs": (),
        },
    }
    engine = ProcessorEngine(accounts)
    blobs = RecordingBlobStore()
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), blobs)

    assert lifecycle.purge_due(now=now) == (expired_id,)
    assert accounts[expired_id]["status"] == "PERMANENTLY_DELETED"
    assert accounts[expired_id]["permanently_deleted_at"] == now
    assert accounts[expired_id]["deletion_outcome"] == "COMPLETED"
    assert accounts[future_id]["status"] == "DELETION_PENDING"
    assert accounts[active_old_id]["status"] == "ACTIVE"
    assert accounts[restored_id]["status"] == "ACTIVE"
    assert blobs.deleted == [
        f"private/{expired_id}/profile",
        f"private/{expired_id}/try-on",
        f"private/previews/{preview_id.hex}",
    ]
    personal_data_mutations = (
        "content_hash = 'deleted-'",
        "DELETE FROM person_profile_images",
        "height_cm = NULL",
        "last_used_at = NULL",
        "quality_details = '{}'::jsonb",
        "DELETE FROM business_user_allowances",
        "UPDATE business_sponsored_sessions",
        "consumer_account_id = NULL",
        "UPDATE business_participants",
        "anonymized_at = COALESCE",
        "DELETE FROM generation_daily_usage",
        "SET normalized_value = 'deleted-'",
        "deletion_outcome = 'COMPLETED'",
        "PERMANENT_DELETION_COMPLETED",
    )
    executed_sql = "\n".join(sql for sql, _ in engine.connection.calls)
    assert all(fragment in executed_sql for fragment in personal_data_mutations)
    forbidden_retained_record_mutations = (
        "DELETE FROM plan_assignments",
        "UPDATE plan_assignments",
        "DELETE FROM ledger_entries",
        "UPDATE ledger_entries",
        "DELETE FROM billable_usage_records",
        "UPDATE billable_usage_records",
        "DELETE FROM invoices",
        "UPDATE invoices",
        "DELETE FROM audit_events",
        "UPDATE audit_events",
        "DELETE FROM consent_records",
        "UPDATE consent_records",
    )
    assert all(fragment not in executed_sql for fragment in forbidden_retained_record_mutations)

    assert lifecycle.purge_due(now=now) == ()
    assert len(blobs.deleted) == 3


def test_scenario_d_deletion_worker_stops_when_login_restores_selected_account() -> None:
    now = datetime(2026, 12, 1, 12, tzinfo=UTC)
    account_id, preview_id = uuid4(), uuid4()
    accounts: dict[UUID, dict[str, Any]] = {
        account_id: {
            "status": "DELETION_PENDING",
            "deletion_at": now - timedelta(seconds=1),
            "media": (f"private/{account_id}/profile", f"private/{account_id}/try-on"),
            "jobs": (preview_id,),
        }
    }
    engine = ProcessorEngine(accounts, restore_before_recheck=account_id)
    blobs = RecordingBlobStore()
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), blobs)

    assert lifecycle.purge_due(now=now) == ()

    assert accounts[account_id]["status"] == "ACTIVE"
    assert accounts[account_id]["deletion_at"] is None
    assert blobs.deleted == []
    forbidden_mutations = (
        "UPDATE media_assets",
        "UPDATE person_profiles",
        "DELETE FROM person_profile_images",
        "UPDATE render_results",
        "DELETE FROM business_user_allowances",
        "UPDATE business_sponsored_sessions",
        "UPDATE business_participants",
        "DELETE FROM generation_daily_usage",
        "UPDATE principal_identities",
        "UPDATE principals",
        "UPDATE sessions",
        "SET status = 'PERMANENTLY_DELETED'",
    )
    assert all(
        not any(fragment in sql for fragment in forbidden_mutations)
        for sql, _ in engine.connection.calls
    )


def test_profile_photo_deletion_failure_is_detectable_and_retryable() -> None:
    now = datetime(2026, 12, 1, 12, tzinfo=UTC)
    account_id = uuid4()
    original_key = f"private/{account_id}/profile"
    accounts: dict[UUID, dict[str, Any]] = {
        account_id: {
            "status": "DELETION_PENDING",
            "deletion_at": now - timedelta(seconds=1),
            "media": (original_key,),
            "jobs": (),
        }
    }
    engine = ProcessorEngine(accounts)
    blobs = RetryableBlobStore(original_key)
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), blobs)

    with pytest.raises(OSError, match="temporary storage failure"):
        lifecycle.purge_due(now=now)

    assert accounts[account_id]["status"] == "DELETION_PENDING"
    assert accounts[account_id].get("permanently_deleted_at") is None
    assert accounts[account_id].get("deletion_outcome") is None
    assert all("PERMANENT_DELETION_COMPLETED" not in sql for sql, _ in engine.connection.calls)
    assert any(
        parameters.get("status") == "FAILED" and parameters.get("failure_code") == "STORAGE_FAILURE"
        for _, parameters in engine.connection.calls
    )
    failure_audits = [
        (sql, parameters)
        for sql, parameters in engine.connection.calls
        if "PERMANENT_DELETION_FAILED" in sql and "WITH interrupted" not in sql
    ]
    assert len(failure_audits) == 1
    assert "source_application" in failure_audits[0][0]
    assert "outcome', 'FAILURE'" in failure_audits[0][0]
    assert "failure_reason" in failure_audits[0][0]
    assert failure_audits[0][1]["failure_code"] == "STORAGE_FAILURE"
    assert original_key not in blobs.items
    assert blobs.items

    assert lifecycle.purge_due(now=now) == (account_id,)
    assert accounts[account_id]["status"] == "PERMANENTLY_DELETED"
    assert accounts[account_id]["permanently_deleted_at"] == now
    assert accounts[account_id]["deletion_outcome"] == "COMPLETED"
    assert blobs.items == set()
    assert any("object_key = NULL" in sql for sql, _ in engine.connection.calls)
    completion_audits = [
        sql for sql, _ in engine.connection.calls if "PERMANENT_DELETION_COMPLETED" in sql
    ]
    assert len(completion_audits) == 1


def test_tryon_preview_timeout_is_recorded_and_retryable() -> None:
    now = datetime(2026, 12, 1, 12, tzinfo=UTC)
    account_id, preview_id = uuid4(), uuid4()
    accounts: dict[UUID, dict[str, Any]] = {
        account_id: {
            "status": "DELETION_PENDING",
            "deletion_at": now - timedelta(seconds=1),
            "media": (f"private/{account_id}/profile",),
            "jobs": (preview_id,),
        }
    }
    engine = ProcessorEngine(accounts)
    blobs = RetryablePreviewBlobStore(preview_id)
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), blobs)

    with pytest.raises(TimeoutError, match="temporary preview deletion timeout"):
        lifecycle.purge_due(now=now)

    assert accounts[account_id]["status"] == "DELETION_PENDING"
    assert any(
        parameters.get("status") == "FAILED" and parameters.get("failure_code") == "TIMEOUT"
        for _, parameters in engine.connection.calls
    )

    assert lifecycle.purge_due(now=now) == (account_id,)
    assert accounts[account_id]["status"] == "PERMANENTLY_DELETED"
    assert accounts[account_id]["deletion_outcome"] == "COMPLETED"
    assert blobs.preview_exists is False
    assert blobs.profile_deletions == 2


def test_database_cleanup_failure_rolls_back_completion_and_retries_safely(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 12, 1, 12, tzinfo=UTC)
    account_id, preview_id = uuid4(), uuid4()
    object_key = f"private/{account_id}/profile"
    preview_key = f"private/previews/{preview_id.hex}"
    blobs = FilesystemPrivateBlobStore(tmp_path)
    blobs.put(object_key, b"profile")
    blobs.put(preview_key, b"try-on")
    accounts: dict[UUID, dict[str, Any]] = {
        account_id: {
            "status": "DELETION_PENDING",
            "deletion_at": now - timedelta(seconds=1),
            "media": (object_key,),
            "jobs": (preview_id,),
        }
    }
    engine = ProcessorEngine(accounts, fail_once_on="DELETE FROM person_profile_images")
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), blobs)

    with pytest.raises(SQLAlchemyError, match="temporary database failure"):
        lifecycle.purge_due(now=now)

    assert accounts[account_id]["status"] == "DELETION_PENDING"
    assert accounts[account_id].get("deletion_outcome") is None
    assert blobs.get(object_key) is None
    assert blobs.get(preview_key) is None
    assert any(
        parameters.get("status") == "FAILED"
        and parameters.get("failure_code") == "DATABASE_FAILURE"
        for _, parameters in engine.connection.calls
    )

    assert lifecycle.purge_due(now=now) == (account_id,)
    assert accounts[account_id]["status"] == "PERMANENTLY_DELETED"
    assert accounts[account_id]["deletion_outcome"] == "COMPLETED"
    assert blobs.get(object_key) is None
    assert blobs.get(preview_key) is None


def test_all_tryon_origins_and_derivatives_become_inaccessible(tmp_path: Path) -> None:
    now = datetime(2026, 12, 1, 12, tzinfo=UTC)
    account_id = uuid4()
    tryon_keys = (
        f"private/{account_id}/b2c-saved-look",
        f"private/{account_id}/b2b2c-boutique-look",
        f"private/{account_id}/b2b2c-jewellery-look",
        f"private/{account_id}/another-business-category-look",
    )
    job_ids = (uuid4(), uuid4())
    derivative_suffixes = ("", ".thumbnail.webp", ".optimized.webp", ".generated-copy.png")
    blobs = FilesystemPrivateBlobStore(tmp_path)
    stored_keys = [f"{key}{suffix}" for key in tryon_keys for suffix in derivative_suffixes] + [
        f"private/previews/{job_id.hex}{suffix}"
        for job_id in job_ids
        for suffix in derivative_suffixes
    ]
    for key in stored_keys:
        blobs.put(key, b"private try-on image")
    accounts: dict[UUID, dict[str, Any]] = {
        account_id: {
            "status": "DELETION_PENDING",
            "deletion_at": now - timedelta(seconds=1),
            "media": tryon_keys,
            "jobs": job_ids,
        }
    }
    engine = ProcessorEngine(accounts)
    lifecycle = PostgresAccountLifecycle(cast(Engine, engine), blobs)

    assert lifecycle.purge_due(now=now) == (account_id,)
    assert all(blobs.get(key) is None for key in stored_keys)
    assert any("object_key = NULL" in sql for sql, _ in engine.connection.calls)

    assert lifecycle.purge_due(now=now) == ()
    assert all(blobs.get(key) is None for key in stored_keys)
