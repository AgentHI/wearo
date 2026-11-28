from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, text

from .retention import PurgeCandidate


class PostgresLifecycleStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def request_owner_deletion(
        self, asset_id: UUID, account_id: UUID, delete_after: datetime
    ) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE media_assets
                    SET deletion_state = 'REQUESTED',
                        delete_after = :delete_after,
                        updated_at = now()
                    WHERE asset_id = :asset
                      AND account_id = :account
                      AND deletion_state = 'RETAINED'
                    RETURNING asset_id
                    """
                ),
                {"asset": asset_id, "account": account_id, "delete_after": delete_after},
            ).scalar_one_or_none()
        return result is not None

    def revoke_access(self, asset_id: UUID, revoked_at: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE media_assets
                    SET deletion_state = 'REQUESTED', updated_at = :revoked_at
                    WHERE asset_id = :asset AND deletion_state = 'RETAINED'
                    """
                ),
                {"asset": asset_id, "revoked_at": revoked_at},
            )

    def due_for_purge(self, at: datetime, limit: int) -> tuple[PurgeCandidate, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("purge limit must be between 1 and 1000")
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                    WITH due AS (
                        SELECT candidate.asset_id
                        FROM media_assets AS candidate
                        WHERE candidate.delete_after <= :at
                          AND candidate.deletion_state IN ('RETAINED', 'REQUESTED')
                          AND candidate.retention_state <> 'LEGAL_HOLD'
                          AND NOT (
                            candidate.purpose = 'SMART_AD'
                            AND (
                              EXISTS (
                                SELECT 1
                                FROM business_smart_ads AS ad
                                WHERE ad.jewellery_asset_id = candidate.asset_id
                                   OR ad.model_asset_id = candidate.asset_id
                                   OR ad.creative_asset_id = candidate.asset_id
                              )
                              OR EXISTS (
                                SELECT 1
                                FROM business_smart_ad_generations AS generation
                                WHERE generation.generated_asset_id = candidate.asset_id
                              )
                            )
                          )
                        ORDER BY candidate.delete_after
                        FOR UPDATE SKIP LOCKED
                        LIMIT :limit
                    )
                    UPDATE media_assets AS asset
                    SET deletion_state = 'QUEUED', updated_at = :at
                    FROM due
                    WHERE asset.asset_id = due.asset_id
                    RETURNING asset.asset_id, asset.account_id, asset.object_key
                    """
                    ),
                    {"at": at, "limit": limit},
                )
                .mappings()
                .all()
            )
        return tuple(
            PurgeCandidate(row["asset_id"], row["account_id"], row["object_key"]) for row in rows
        )

    def mark_deleted(self, asset_id: UUID, deleted_at: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE media_assets
                    SET deletion_state = 'DELETED',
                        object_key = NULL,
                        deleted_at = :deleted_at,
                        updated_at = :deleted_at
                    WHERE asset_id = :asset AND deletion_state = 'QUEUED'
                    """
                ),
                {"asset": asset_id, "deleted_at": deleted_at},
            )

    def mark_purge_failed(self, asset_id: UUID, failed_at: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE media_assets
                    SET deletion_state = 'REQUESTED', updated_at = :failed_at
                    WHERE asset_id = :asset AND deletion_state = 'QUEUED'
                    """
                ),
                {"asset": asset_id, "failed_at": failed_at},
            )
