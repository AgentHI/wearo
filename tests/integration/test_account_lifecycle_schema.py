from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text

from apps.api.wearo_api.account_lifecycle import AccountLifecycleError, PostgresAccountLifecycle
from apps.api.wearo_api.database import normalize_database_url

pytestmark = pytest.mark.integration


class RecordingBlobStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_asset_family(self, key: str) -> None:
        self.deleted.append(key)

    def delete_render_preview(self, job_id: UUID) -> None:
        self.deleted.append(f"private/previews/{job_id.hex}")


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


def test_account_cancellation_retains_media_for_exactly_thirty_days(engine: Engine) -> None:
    account_id, principal_id, identity_id = uuid4(), uuid4(), uuid4()
    other_account_id, other_principal_id = uuid4(), uuid4()
    assignment_id, future_assignment_id = uuid4(), uuid4()
    person_asset_id, result_asset_id = uuid4(), uuid4()
    consent_id, profile_id, profile_image_id = uuid4(), uuid4(), uuid4()
    cancelled_at = datetime(2026, 10, 25, 9, 15, tzinfo=UTC)
    blob_store = RecordingBlobStore()
    lifecycle = PostgresAccountLifecycle(engine, blob_store)

    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
            {"account": account_id},
        )
        connection.execute(
            text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
            {"account": other_account_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO principals
                    (principal_id, account_id, account_kind, principal_type)
                VALUES (:principal, :account, 'CONSUMER', 'CONSUMER')
                """
            ),
            {"principal": principal_id, "account": account_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO principals
                    (principal_id, account_id, account_kind, principal_type)
                VALUES (:principal, :account, 'CONSUMER', 'CONSUMER')
                """
            ),
            {"principal": other_principal_id, "account": other_account_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO principal_identities
                    (identity_id, account_id, principal_id, channel, normalized_value)
                VALUES (:identity, :account, :principal, 'EMAIL', :email)
                """
            ),
            {
                "identity": identity_id,
                "account": account_id,
                "principal": principal_id,
                "email": f"cancel-{identity_id.hex}@example.com",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO plan_assignments
                    (assignment_id, account_id, plan_code, effective_from)
                VALUES
                    (:assignment, :account, 'BETA', :effective_from),
                    (:future_assignment, :account, 'RENEWAL', :future_effective_from)
                """
            ),
            {
                "assignment": assignment_id,
                "future_assignment": future_assignment_id,
                "account": account_id,
                "effective_from": cancelled_at - timedelta(days=5),
                "future_effective_from": cancelled_at + timedelta(days=25),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO media_assets
                    (asset_id, account_id, object_key, content_hash, mime_type, purpose)
                VALUES
                    (:person, :account, :person_key, :person_hash, 'image/png', 'PERSON_SOURCE'),
                    (:result, :account, :result_key, :result_hash, 'image/png', 'RENDER_RESULT')
                """
            ),
            {
                "person": person_asset_id,
                "result": result_asset_id,
                "account": account_id,
                "person_key": f"private/{account_id.hex}/{person_asset_id.hex}",
                "result_key": f"private/{account_id.hex}/{result_asset_id.hex}",
                "person_hash": "1" * 64,
                "result_hash": "2" * 64,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO consent_records
                    (consent_id, account_id, asset_id, actor_principal_id,
                     consent_version, purpose, permission_asserted, accepted_at)
                VALUES
                    (:consent, :account, :asset, :principal,
                     'beta-v1', 'TRY_ON', true, :accepted_at)
                """
            ),
            {
                "consent": consent_id,
                "account": account_id,
                "asset": person_asset_id,
                "principal": principal_id,
                "accepted_at": cancelled_at - timedelta(days=10),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO person_profiles
                    (profile_id, account_id, principal_id, person_asset_id, consent_id,
                     height_cm, weight_kg, last_used_at)
                VALUES
                    (:profile, :account, :principal, :asset, :consent, 171.5, 68.2, :last_used)
                """
            ),
            {
                "profile": profile_id,
                "account": account_id,
                "principal": principal_id,
                "asset": person_asset_id,
                "consent": consent_id,
                "last_used": cancelled_at - timedelta(days=1),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO person_profile_images
                    (profile_image_id, profile_id, account_id, asset_id, consent_id,
                     photo_type, label, is_primary)
                VALUES
                    (:image, :profile, :account, :asset, :consent,
                     'FULL_BODY', 'My primary full-body photo', true)
                """
            ),
            {
                "image": profile_image_id,
                "profile": profile_id,
                "account": account_id,
                "asset": person_asset_id,
                "consent": consent_id,
            },
        )

    try:
        with pytest.raises(AccountLifecycleError) as ownership_error:
            lifecycle.cancel(account_id, other_principal_id, now=cancelled_at)
        assert ownership_error.value.code == "ACCOUNT_CANCELLATION_UNAVAILABLE"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT status FROM accounts WHERE account_id = :account"),
                    {"account": account_id},
                ).scalar_one()
                == "ACTIVE"
            )

        result = lifecycle.cancel(account_id, principal_id, now=cancelled_at)

        assert result.status == "DELETION_PENDING"
        assert result.cancellation_at == cancelled_at
        assert result.deletion_at == cancelled_at + timedelta(days=30)
        assert blob_store.deleted == []

        restarted_lifecycle = PostgresAccountLifecycle(engine, RecordingBlobStore())
        assert restarted_lifecycle.get(account_id, principal_id) == result
        duplicate = restarted_lifecycle.cancel(
            account_id,
            principal_id,
            now=cancelled_at + timedelta(days=7),
        )
        assert duplicate == result

        with engine.connect() as connection:
            account = (
                connection.execute(
                    text(
                        """
                    SELECT status, cancellation_at, deletion_at
                    FROM accounts WHERE account_id = :account
                    """
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one()
            )
            media = tuple(
                connection.execute(
                    text(
                        """
                        SELECT purpose, deletion_state, deleted_at FROM media_assets
                        WHERE account_id = :account ORDER BY purpose
                        """
                    ),
                    {"account": account_id},
                ).mappings()
            )
            plans = tuple(
                connection.execute(
                    text(
                        """
                        SELECT assignment_id, effective_until, cancelled_at
                        FROM plan_assignments WHERE account_id = :account
                        ORDER BY effective_from
                        """
                    ),
                    {"account": account_id},
                ).mappings()
            )
            cancellation_audit_count: int = connection.execute(
                text(
                    """
                    SELECT count(*) FROM audit_events
                    WHERE account_id = :account
                      AND action = 'ACCOUNT_MARKED_FOR_DELETION'
                    """
                ),
                {"account": account_id},
            ).scalar_one()

        assert account["status"] == "DELETION_PENDING"
        assert account["cancellation_at"] == cancelled_at
        assert account["deletion_at"] - account["cancellation_at"] == timedelta(days=30)
        assert len(plans) == 2
        assert plans[0]["assignment_id"] == assignment_id
        assert plans[0]["effective_until"] == cancelled_at
        assert plans[0]["cancelled_at"] == cancelled_at
        assert plans[1]["assignment_id"] == future_assignment_id
        assert plans[1]["effective_until"] is None
        assert plans[1]["cancelled_at"] == cancelled_at
        assert cancellation_audit_count == 1
        assert {row["purpose"] for row in media} == {"PERSON_SOURCE", "RENDER_RESULT"}
        assert all(row["deletion_state"] == "RETAINED" for row in media)
        assert all(row["deleted_at"] is None for row in media)

        restored_at = cancelled_at + timedelta(days=7)
        assert lifecycle.restore(account_id, principal_id, now=restored_at) == result.deletion_at
        with engine.connect() as connection:
            restored_account = (
                connection.execute(
                    text(
                        """
                        SELECT status, cancellation_at, deletion_at
                        FROM accounts WHERE account_id = :account
                        """
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one()
            )
            restored_media = tuple(
                connection.execute(
                    text(
                        """
                        SELECT purpose, deletion_state, deleted_at FROM media_assets
                        WHERE account_id = :account ORDER BY purpose
                        """
                    ),
                    {"account": account_id},
                ).mappings()
            )
            restored_plans = tuple(
                connection.execute(
                    text(
                        """
                        SELECT effective_until, cancelled_at FROM plan_assignments
                        WHERE account_id = :account ORDER BY effective_from
                        """
                    ),
                    {"account": account_id},
                ).mappings()
            )
            restoration_audit_count: int = connection.execute(
                text(
                    """
                    SELECT count(*) FROM audit_events
                    WHERE account_id = :account
                      AND action = 'ACCOUNT_RESTORED'
                    """
                ),
                {"account": account_id},
            ).scalar_one()

        assert restored_account["status"] == "ACTIVE"
        assert restored_account["cancellation_at"] is None
        assert restored_account["deletion_at"] is None
        assert {row["purpose"] for row in restored_media} == {
            "PERSON_SOURCE",
            "RENDER_RESULT",
        }
        assert all(row["deletion_state"] == "RETAINED" for row in restored_media)
        assert all(row["deleted_at"] is None for row in restored_media)
        assert all(row["cancelled_at"] == cancelled_at for row in restored_plans)
        assert restoration_audit_count == 1
        assert lifecycle.purge_due(now=result.deletion_at + timedelta(days=1)) == ()
        assert blob_store.deleted == []

        recancelled = lifecycle.cancel(
            account_id,
            principal_id,
            now=cancelled_at + timedelta(days=8),
        )
        assert recancelled.status == "DELETION_PENDING"
        assert recancelled.deletion_at is not None
        assert lifecycle.purge_due(now=recancelled.deletion_at - timedelta(microseconds=1)) == ()
        assert lifecycle.purge_due(now=recancelled.deletion_at) == (account_id,)
        assert len(blob_store.deleted) == 2
        with engine.connect() as connection:
            final_account = (
                connection.execute(
                    text(
                        """
                        SELECT status, permanently_deleted_at, deletion_outcome
                        FROM accounts WHERE account_id = :account
                        """
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one()
            )
            assert final_account["status"] == "PERMANENTLY_DELETED"
            assert final_account["permanently_deleted_at"] == recancelled.deletion_at
            assert final_account["deletion_outcome"] == "COMPLETED"
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM media_assets "
                        "WHERE account_id = :account AND deletion_state = 'DELETED'"
                    ),
                    {"account": account_id},
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text(
                        """
                        SELECT count(*) FROM audit_events
                        WHERE account_id = :account
                          AND action = 'PERMANENT_DELETION_COMPLETED'
                          AND actor_type = 'SYSTEM'
                          AND actor_id IS NULL
                          AND after_summary->>'deletion_outcome' = 'COMPLETED'
                        """
                    ),
                    {"account": account_id},
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        """
                        SELECT count(*) FROM account_deletion_attempts
                        WHERE account_id = :account AND status = 'COMPLETED'
                          AND failure_code IS NULL AND completed_at IS NOT NULL
                        """
                    ),
                    {"account": account_id},
                ).scalar_one()
                == 1
            )
            deleted_profile = (
                connection.execute(
                    text(
                        """
                        SELECT status, height_cm, weight_kg, last_used_at
                        FROM person_profiles WHERE account_id = :account
                        """
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one()
            )
            assert deleted_profile["status"] == "DELETED"
            assert deleted_profile["height_cm"] is None
            assert deleted_profile["weight_kg"] is None
            assert deleted_profile["last_used_at"] is None
            assert (
                connection.execute(
                    text("SELECT count(*) FROM person_profile_images WHERE account_id = :account"),
                    {"account": account_id},
                ).scalar_one()
                == 0
            )
            identity = (
                connection.execute(
                    text(
                        """
                        SELECT normalized_value, verified_at FROM principal_identities
                        WHERE account_id = :account
                        """
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one()
            )
            assert identity["normalized_value"].startswith("deleted-")
            assert identity["verified_at"] is None
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM media_assets "
                        "WHERE account_id = :account AND object_key IS NULL"
                    ),
                    {"account": account_id},
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM plan_assignments WHERE account_id = :account"),
                    {"account": account_id},
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text(
                        """
                        SELECT count(*) FROM audit_events
                        WHERE account_id = :account
                          AND action = 'ACCOUNT_MARKED_FOR_DELETION'
                        """
                    ),
                    {"account": account_id},
                ).scalar_one()
                == 2
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE audit_events DISABLE TRIGGER trg_audit_events_immutable")
            )
            try:
                connection.execute(
                    text("DELETE FROM audit_events WHERE account_id = :account"),
                    {"account": account_id},
                )
            finally:
                connection.execute(
                    text("ALTER TABLE audit_events ENABLE TRIGGER trg_audit_events_immutable")
                )
            connection.execute(
                text("DELETE FROM plan_assignments WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM account_deletion_attempts WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM person_profile_images WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM person_profiles WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("ALTER TABLE consent_records DISABLE TRIGGER trg_consent_records_immutable")
            )
            try:
                connection.execute(
                    text("DELETE FROM consent_records WHERE account_id = :account"),
                    {"account": account_id},
                )
            finally:
                connection.execute(
                    text("ALTER TABLE consent_records ENABLE TRIGGER trg_consent_records_immutable")
                )
            connection.execute(
                text("DELETE FROM media_assets WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM principal_identities WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM principals WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM principals WHERE account_id = :account"),
                {"account": other_account_id},
            )
            connection.execute(
                text("DELETE FROM accounts WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM accounts WHERE account_id = :account"),
                {"account": other_account_id},
            )
