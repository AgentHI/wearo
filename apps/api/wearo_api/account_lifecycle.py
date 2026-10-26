from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

AccountLifecycleState = Literal["ACTIVE", "DELETION_PENDING", "PERMANENTLY_DELETED"]
DeletionOutcome = Literal["COMPLETED"]
DELETION_GRACE_PERIOD = timedelta(days=30)


class AccountLifecycleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AccountBlobStore(Protocol):
    def delete_asset_family(self, key: str) -> None: ...

    def delete_render_preview(self, job_id: UUID) -> None: ...


@dataclass(frozen=True)
class AccountLifecycle:
    account_id: UUID
    status: AccountLifecycleState
    cancellation_at: datetime | None
    deletion_at: datetime | None
    permanently_deleted_at: datetime | None = None
    deletion_outcome: DeletionOutcome | None = None


def deletion_eligibility(cancellation_at: datetime) -> datetime:
    if cancellation_at.tzinfo is None or cancellation_at.utcoffset() is None:
        raise ValueError("cancellation timestamp must be timezone-aware")
    return cancellation_at + DELETION_GRACE_PERIOD


class PostgresAccountLifecycle:
    """Coordinates billing shutdown, retention, and irreversible account deletion."""

    def __init__(self, engine: Engine, blobs: AccountBlobStore) -> None:
        self.engine = engine
        self.blobs = blobs

    @staticmethod
    def _failure_code(error: Exception) -> str:
        if isinstance(error, TimeoutError):
            return "TIMEOUT"
        if isinstance(error, ConnectionError):
            return "SERVICE_UNAVAILABLE"
        if isinstance(error, SQLAlchemyError):
            return "DATABASE_FAILURE"
        if isinstance(error, OSError):
            return "STORAGE_FAILURE"
        return "UNEXPECTED_FAILURE"

    def _start_deletion_attempt(self, account_id: UUID, current: datetime) -> UUID:
        attempt_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    WITH interrupted AS (
                        UPDATE account_deletion_attempts
                        SET status = 'FAILED', failure_code = 'INTERRUPTED', completed_at = :now,
                            updated_at = :now
                        WHERE account_id = :account AND status = 'RUNNING'
                        RETURNING account_id, attempt_id
                    )
                    INSERT INTO audit_events
                        (account_id, actor_type, action, target_type, target_id,
                         reason, after_summary, occurred_at)
                    SELECT interrupted.account_id, 'SYSTEM', 'PERMANENT_DELETION_FAILED',
                           'ACCOUNT', interrupted.account_id,
                           'An interrupted permanent deletion attempt remains retryable.',
                           jsonb_build_object(
                              'source_application', CASE WHEN EXISTS (
                                  SELECT 1 FROM business_participants
                                  WHERE consumer_account_id = interrupted.account_id
                              ) THEN 'B2B2C' ELSE 'B2C' END,
                              'outcome', 'FAILURE',
                              'failure_reason', 'INTERRUPTED',
                              'attempt_id', interrupted.attempt_id
                           ), :now
                    FROM interrupted
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO account_deletion_attempts
                        (attempt_id, account_id, status, started_at)
                    VALUES (:attempt, :account, 'RUNNING', :now)
                    """
                ),
                {"attempt": attempt_id, "account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (account_id, actor_type, action, target_type, target_id,
                         reason, after_summary, occurred_at)
                    VALUES
                        (:account, 'SYSTEM', 'PERMANENT_DELETION_STARTED',
                         'ACCOUNT', :account, 'Scheduled permanent deletion started.',
                         jsonb_build_object(
                            'source_application', CASE WHEN EXISTS (
                                SELECT 1 FROM business_participants
                                WHERE consumer_account_id = :account
                            ) THEN 'B2B2C' ELSE 'B2C' END,
                            'outcome', 'SUCCESS',
                            'attempt_id', :attempt
                         ), :now)
                    """
                ),
                {"attempt": attempt_id, "account": account_id, "now": current},
            )
        return attempt_id

    def _finish_deletion_attempt(
        self, attempt_id: UUID, current: datetime, status: str, failure_code: str | None = None
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE account_deletion_attempts
                    SET status = :status, failure_code = :failure_code, completed_at = :now,
                        updated_at = :now
                    WHERE attempt_id = :attempt AND status = 'RUNNING'
                    """
                ),
                {
                    "attempt": attempt_id,
                    "status": status,
                    "failure_code": failure_code,
                    "now": current,
                },
            )
            if status == "FAILED":
                connection.execute(
                    text(
                        """
                        INSERT INTO audit_events
                            (account_id, actor_type, action, target_type, target_id,
                             reason, after_summary, occurred_at)
                        SELECT attempt.account_id, 'SYSTEM',
                               'PERMANENT_DELETION_FAILED', 'ACCOUNT', attempt.account_id,
                               'Scheduled permanent deletion failed and remains retryable.',
                               jsonb_build_object(
                                  'source_application', COALESCE((
                                      SELECT started.after_summary->>'source_application'
                                      FROM audit_events started
                                      WHERE started.account_id = attempt.account_id
                                        AND started.action = 'PERMANENT_DELETION_STARTED'
                                        AND started.after_summary->>'attempt_id' = :attempt_text
                                      LIMIT 1
                                  ), 'B2C'),
                                  'outcome', 'FAILURE',
                                  'failure_reason', :failure_code,
                                  'attempt_id', :attempt
                               ), :now
                        FROM account_deletion_attempts attempt
                        WHERE attempt.attempt_id = :attempt
                        """
                    ),
                    {
                        "attempt": attempt_id,
                        "attempt_text": str(attempt_id),
                        "failure_code": failure_code,
                        "now": current,
                    },
                )

    def cancel(
        self, account_id: UUID, principal_id: UUID, *, now: datetime | None = None
    ) -> AccountLifecycle:
        cancelled_at = now or datetime.now(UTC)
        delete_at = deletion_eligibility(cancelled_at)
        with self.engine.begin() as connection:
            account = (
                connection.execute(
                    text(
                        """
                        SELECT a.status, a.cancellation_at, a.deletion_at,
                               a.permanently_deleted_at, a.deletion_outcome,
                               p.status AS principal_status
                        FROM accounts a
                        JOIN principals p ON p.account_id = a.account_id
                        WHERE a.account_id = :account AND p.principal_id = :principal
                        FOR UPDATE OF a
                        """
                    ),
                    {"account": account_id, "principal": principal_id},
                )
                .mappings()
                .one_or_none()
            )
            if account is None:
                raise AccountLifecycleError(
                    "ACCOUNT_CANCELLATION_UNAVAILABLE", "Account cancellation is unavailable."
                )

            if account["status"] in {"DELETION_PENDING", "PERMANENTLY_DELETED"}:
                return AccountLifecycle(
                    account_id=account_id,
                    status=account["status"],
                    cancellation_at=account["cancellation_at"],
                    deletion_at=account["deletion_at"],
                    permanently_deleted_at=account["permanently_deleted_at"],
                    deletion_outcome=account["deletion_outcome"],
                )

            if account["status"] != "ACTIVE" or account["principal_status"] != "ACTIVE":
                raise AccountLifecycleError(
                    "ACCOUNT_CANCELLATION_UNAVAILABLE", "Account cancellation is unavailable."
                )

            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (account_id, actor_type, actor_id, action, target_type, target_id,
                         reason, after_summary, occurred_at)
                    VALUES
                        (:account, 'PRINCIPAL', :principal,
                         'SUBSCRIPTION_CANCELLATION_REQUESTED', 'ACCOUNT', :account,
                         'User explicitly requested subscription cancellation.',
                         jsonb_build_object(
                            'source_application', CASE WHEN EXISTS (
                                SELECT 1 FROM business_participants
                                WHERE consumer_account_id = :account
                            ) THEN 'B2B2C' ELSE 'B2C' END,
                            'outcome', 'SUCCESS'
                         ), :cancelled_at)
                    """
                ),
                {
                    "account": account_id,
                    "principal": principal_id,
                    "cancelled_at": cancelled_at,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE plan_assignments
                    SET cancelled_at = COALESCE(cancelled_at, :cancelled_at),
                        effective_until = CASE
                            WHEN effective_from < :cancelled_at
                              AND (effective_until IS NULL OR effective_until > :cancelled_at)
                            THEN :cancelled_at
                            ELSE effective_until
                        END,
                        updated_at = :cancelled_at
                    WHERE account_id = :account AND cancelled_at IS NULL
                    """
                ),
                {"account": account_id, "cancelled_at": cancelled_at},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (account_id, actor_type, actor_id, action, target_type, target_id,
                         reason, after_summary, occurred_at)
                    VALUES
                        (:account, 'PRINCIPAL', :principal, 'SUBSCRIPTION_CANCELLED',
                         'ACCOUNT', :account, 'Subscription renewal and charging stopped.',
                         jsonb_build_object(
                            'source_application', CASE WHEN EXISTS (
                                SELECT 1 FROM business_participants
                                WHERE consumer_account_id = :account
                            ) THEN 'B2B2C' ELSE 'B2C' END,
                            'outcome', 'SUCCESS'
                         ), :cancelled_at)
                    """
                ),
                {
                    "account": account_id,
                    "principal": principal_id,
                    "cancelled_at": cancelled_at,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE offering_entitlements
                    SET enabled = false, effective_until = CASE
                            WHEN effective_from < :cancelled_at THEN :cancelled_at
                            ELSE effective_until
                        END,
                        updated_at = :cancelled_at
                    WHERE account_id = :account AND enabled
                    """
                ),
                {"account": account_id, "cancelled_at": cancelled_at},
            )
            connection.execute(
                text(
                    """
                    UPDATE accounts
                    SET status = 'DELETION_PENDING', cancellation_at = :cancelled_at,
                        deletion_at = :delete_at, permanently_deleted_at = NULL,
                        deletion_outcome = NULL, updated_at = :cancelled_at
                    WHERE account_id = :account
                    """
                ),
                {
                    "account": account_id,
                    "cancelled_at": cancelled_at,
                    "delete_at": delete_at,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (account_id, actor_type, actor_id, action, target_type, target_id,
                         reason, before_summary, after_summary, occurred_at)
                    VALUES
                        (:account, 'PRINCIPAL', :principal, 'ACCOUNT_MARKED_FOR_DELETION',
                         'ACCOUNT', :account, 'Account entered its deletion grace period.',
                         jsonb_build_object('status', 'ACTIVE'),
                         jsonb_build_object(
                            'status', 'DELETION_PENDING',
                            'cancellation_at', :cancelled_at,
                            'deletion_at', :delete_at,
                            'source_application', CASE WHEN EXISTS (
                                SELECT 1 FROM business_participants
                                WHERE consumer_account_id = :account
                            ) THEN 'B2B2C' ELSE 'B2C' END,
                            'outcome', 'SUCCESS'
                         ), :cancelled_at)
                    """
                ),
                {
                    "account": account_id,
                    "principal": principal_id,
                    "cancelled_at": cancelled_at,
                    "delete_at": delete_at,
                },
            )
        return AccountLifecycle(
            account_id=account_id,
            status="DELETION_PENDING",
            cancellation_at=cancelled_at,
            deletion_at=delete_at,
        )

    def get(self, account_id: UUID, principal_id: UUID) -> AccountLifecycle:
        with self.engine.connect() as connection:
            account = (
                connection.execute(
                    text(
                        """
                        SELECT a.status, a.cancellation_at, a.deletion_at,
                               a.permanently_deleted_at, a.deletion_outcome
                        FROM accounts a
                        JOIN principals p ON p.account_id = a.account_id
                        WHERE a.account_id = :account AND p.principal_id = :principal
                        """
                    ),
                    {"account": account_id, "principal": principal_id},
                )
                .mappings()
                .one_or_none()
            )
        if account is None or account["status"] not in {
            "ACTIVE",
            "DELETION_PENDING",
            "PERMANENTLY_DELETED",
        }:
            raise AccountLifecycleError(
                "ACCOUNT_LIFECYCLE_UNAVAILABLE", "Account lifecycle is unavailable."
            )
        return AccountLifecycle(
            account_id=account_id,
            status=account["status"],
            cancellation_at=account["cancellation_at"],
            deletion_at=account["deletion_at"],
            permanently_deleted_at=account["permanently_deleted_at"],
            deletion_outcome=account["deletion_outcome"],
        )

    def restore(
        self, account_id: UUID, principal_id: UUID, *, now: datetime | None = None
    ) -> datetime:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            account = (
                connection.execute(
                    text(
                        """
                        SELECT a.status, a.deletion_at
                        FROM accounts a
                        JOIN principals p ON p.account_id = a.account_id
                        WHERE a.account_id = :account AND p.principal_id = :principal
                          AND p.status = 'ACTIVE'
                        FOR UPDATE OF a
                        """
                    ),
                    {"account": account_id, "principal": principal_id},
                )
                .mappings()
                .one_or_none()
            )
            if (
                account is None
                or account["status"] != "DELETION_PENDING"
                or account["deletion_at"] <= current
            ):
                raise AccountLifecycleError(
                    "ACCOUNT_RESTORATION_UNAVAILABLE", "Account restoration is unavailable."
                )
            scheduled_deletion_at: datetime = account["deletion_at"]
            connection.execute(
                text(
                    """
                    UPDATE accounts
                    SET status = 'ACTIVE', cancellation_at = NULL, deletion_at = NULL,
                        permanently_deleted_at = NULL, deletion_outcome = NULL,
                        updated_at = :now
                    WHERE account_id = :account AND status = 'DELETION_PENDING'
                      AND deletion_at > :now
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (account_id, actor_type, actor_id, action, target_type, target_id,
                         reason, before_summary, after_summary, occurred_at)
                    VALUES
                        (:account, 'PRINCIPAL', :principal, 'ACCOUNT_RESTORED',
                         'ACCOUNT', :account, 'User signed in during the deletion grace period.',
                         jsonb_build_object(
                            'status', 'DELETION_PENDING',
                            'deletion_at', :deletion_at
                         ), jsonb_build_object(
                            'status', 'ACTIVE',
                            'source_application', CASE WHEN EXISTS (
                                SELECT 1 FROM business_participants
                                WHERE consumer_account_id = :account
                            ) THEN 'B2B2C' ELSE 'B2C' END,
                            'outcome', 'SUCCESS'
                         ), :now)
                    """
                ),
                {
                    "account": account_id,
                    "principal": principal_id,
                    "deletion_at": scheduled_deletion_at,
                    "now": current,
                },
            )
        return scheduled_deletion_at

    def purge_due(self, *, now: datetime | None = None, limit: int = 100) -> tuple[UUID, ...]:
        """Permanently delete only accounts whose full grace period has elapsed."""
        if limit < 1:
            raise ValueError("limit must be positive")
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            account_ids: tuple[UUID, ...] = tuple(
                connection.execute(
                    text(
                        """
                        SELECT account_id FROM accounts
                        WHERE status = 'DELETION_PENDING' AND deletion_at <= :now
                        ORDER BY deletion_at, account_id
                        LIMIT :limit
                        """
                    ),
                    {"now": current, "limit": limit},
                ).scalars()
            )
        deleted_account_ids: list[UUID] = []
        for account_id in account_ids:
            attempt_id = self._start_deletion_attempt(account_id, current)
            try:
                deleted = self._purge_account(account_id, attempt_id, current)
            except Exception as error:
                self._finish_deletion_attempt(
                    attempt_id, current, "FAILED", self._failure_code(error)
                )
                raise
            if deleted:
                deleted_account_ids.append(account_id)
            else:
                self._finish_deletion_attempt(attempt_id, current, "SKIPPED", "ELIGIBILITY_CHANGED")
        return tuple(deleted_account_ids)

    def _purge_account(self, account_id: UUID, attempt_id: UUID, current: datetime) -> bool:
        with self.engine.begin() as connection:
            media: tuple[str, ...] = tuple(
                connection.execute(
                    text(
                        """
                        SELECT object_key FROM media_assets
                        WHERE account_id = :account AND deletion_state <> 'DELETED'
                        FOR UPDATE
                        """
                    ),
                    {"account": account_id},
                ).scalars()
            )
            previews: tuple[UUID, ...] = tuple(
                connection.execute(
                    text("SELECT job_id FROM render_jobs WHERE account_id = :account"),
                    {"account": account_id},
                ).scalars()
            )
            account = (
                connection.execute(
                    text(
                        """
                        SELECT status, deletion_at FROM accounts
                        WHERE account_id = :account
                          AND status = 'DELETION_PENDING'
                          AND deletion_at <= :now
                        FOR UPDATE
                        """
                    ),
                    {"account": account_id, "now": current},
                )
                .mappings()
                .one_or_none()
            )
            if (
                account is None
                or account["status"] != "DELETION_PENDING"
                or account["deletion_at"] is None
                or account["deletion_at"] > current
            ):
                return False
            for object_key in media:
                self.blobs.delete_asset_family(object_key)
            for job_id in previews:
                self.blobs.delete_render_preview(job_id)

            connection.execute(
                text(
                    """
                    UPDATE media_assets
                    SET object_key = NULL,
                        content_hash = 'deleted-' || asset_id::text,
                        mime_type = 'application/octet-stream',
                        deletion_state = 'DELETED', deleted_at = :now,
                        delete_after = COALESCE(delete_after, :now), updated_at = :now
                    WHERE account_id = :account AND deletion_state <> 'DELETED'
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text("DELETE FROM person_profile_images WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text(
                    """
                    UPDATE person_profiles
                    SET status = 'DELETED', height_cm = NULL, weight_kg = NULL,
                        last_used_at = NULL,
                        delete_after = COALESCE(delete_after, :now),
                        deleted_at = COALESCE(deleted_at, :now), updated_at = :now
                    WHERE account_id = :account
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    UPDATE render_results
                    SET quality_details = '{}'::jsonb, provider_request_id = NULL,
                        updated_at = :now
                    WHERE account_id = :account
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    DELETE FROM business_user_allowances allowance
                    USING business_participants participant
                    WHERE participant.consumer_account_id = :account
                      AND allowance.tenant_id = participant.tenant_id
                      AND allowance.normalized_mobile = participant.normalized_mobile
                    """
                ),
                {"account": account_id},
            )
            connection.execute(
                text(
                    """
                    UPDATE business_sponsored_sessions
                    SET consumer_account_id = NULL, consumer_principal_id = NULL,
                        status = 'EXPIRED', updated_at = :now
                    WHERE consumer_account_id = :account
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    UPDATE business_participants
                    SET normalized_mobile = md5(participant_id::text),
                        normalized_email = NULL,
                        consumer_account_id = NULL, consumer_principal_id = NULL,
                        first_seen_at = :now, latest_seen_at = :now,
                        anonymized_at = COALESCE(anonymized_at, :now)
                    WHERE consumer_account_id = :account
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text("DELETE FROM generation_daily_usage WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text(
                    """
                    UPDATE principal_identities
                    SET normalized_value = 'deleted-' || identity_id::text || '@invalid.local',
                        verified_at = NULL, updated_at = :now
                    WHERE account_id = :account
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    UPDATE principals SET status = 'CLOSED', updated_at = :now
                    WHERE account_id = :account
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    UPDATE sessions
                    SET revoked_at = COALESCE(revoked_at, :now), updated_at = :now
                    WHERE account_id = :account AND revoked_at IS NULL
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    UPDATE accounts
                    SET status = 'PERMANENTLY_DELETED', permanently_deleted_at = :now,
                        deletion_outcome = 'COMPLETED', updated_at = :now
                    WHERE account_id = :account AND status = 'DELETION_PENDING'
                      AND deletion_at <= :now
                    """
                ),
                {"account": account_id, "now": current},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (account_id, actor_type, action, target_type, target_id,
                         reason, before_summary, after_summary, occurred_at)
                    VALUES
                        (:account, 'SYSTEM', 'PERMANENT_DELETION_COMPLETED',
                         'ACCOUNT', :account,
                         'Scheduled account deletion completed successfully.',
                         jsonb_build_object(
                            'status', 'DELETION_PENDING',
                            'deletion_at', :deletion_at
                         ),
                         jsonb_build_object(
                            'status', 'PERMANENTLY_DELETED',
                            'deletion_outcome', 'COMPLETED',
                            'permanently_deleted_at', :now,
                            'source_application', COALESCE((
                                SELECT started.after_summary->>'source_application'
                                FROM audit_events started
                                WHERE started.account_id = :account
                                  AND started.action = 'PERMANENT_DELETION_STARTED'
                                  AND started.after_summary->>'attempt_id' = :attempt_text
                                LIMIT 1
                            ), 'B2C'),
                            'outcome', 'SUCCESS',
                            'attempt_id', :attempt
                         ), :now)
                    """
                ),
                {
                    "account": account_id,
                    "deletion_at": account["deletion_at"],
                    "attempt": attempt_id,
                    "attempt_text": str(attempt_id),
                    "now": current,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE account_deletion_attempts
                    SET status = 'COMPLETED', failure_code = NULL, completed_at = :now,
                        updated_at = :now
                    WHERE attempt_id = :attempt AND status = 'RUNNING'
                    """
                ),
                {"attempt": attempt_id, "now": current},
            )
        return True
