from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .beta_profile import DailyUsage, PersonProfile, ProfileImage
from .consent import ConsentEvidence, ConsentPurpose
from .render_preflight import BetaRenderQuote


def _profile(row: object, images: tuple[ProfileImage, ...] = ()) -> PersonProfile:
    values = row._mapping  # type: ignore[attr-defined]
    return PersonProfile(
        profile_id=values["profile_id"],
        account_id=values["account_id"],
        principal_id=values["principal_id"],
        person_asset_id=values["person_asset_id"],
        consent_id=values["consent_id"],
        height_cm=values["height_cm"],
        weight_kg=values["weight_kg"],
        status=values["status"],
        last_used_at=values["last_used_at"],
        images=images,
    )


class PostgresProfileStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def replace_active(self, profile: PersonProfile, replaced_at: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE person_profiles
                    SET status = 'DELETION_REQUESTED',
                        delete_after = :delete_after,
                        updated_at = :replaced_at
                    WHERE account_id = :account AND status = 'ACTIVE'
                    """
                ),
                {
                    "account": profile.account_id,
                    "replaced_at": replaced_at,
                    "delete_after": replaced_at + timedelta(hours=24),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO person_profiles
                        (
                            profile_id,
                            account_id,
                            principal_id,
                            person_asset_id,
                            consent_id,
                            height_cm,
                            weight_kg,
                            status,
                            last_used_at
                        )
                    VALUES
                        (
                            :profile,
                            :account,
                            :principal,
                            :person_asset,
                            :consent,
                            :height,
                            :weight,
                            'ACTIVE',
                            :last_used
                        )
                    """
                ),
                {
                    "profile": profile.profile_id,
                    "account": profile.account_id,
                    "principal": profile.principal_id,
                    "person_asset": profile.person_asset_id,
                    "consent": profile.consent_id,
                    "height": profile.height_cm,
                    "weight": profile.weight_kg,
                    "last_used": profile.last_used_at,
                },
            )
            images = profile.images or (
                ProfileImage(
                    profile_image_id=uuid4(),
                    asset_id=profile.person_asset_id,
                    consent_id=profile.consent_id,
                    photo_type="FULL_BODY",
                    label="Full body",
                    is_primary=True,
                ),
            )
            connection.execute(
                text(
                    """
                    INSERT INTO person_profile_images
                        (
                            profile_image_id,
                            profile_id,
                            account_id,
                            asset_id,
                            consent_id,
                            photo_type,
                            label,
                            is_primary
                        )
                    VALUES
                        (
                            :profile_image,
                            :profile,
                            :account,
                            :asset,
                            :consent,
                            :photo_type,
                            :label,
                            :is_primary
                        )
                    """
                ),
                [
                    {
                        "profile_image": image.profile_image_id,
                        "profile": profile.profile_id,
                        "account": profile.account_id,
                        "asset": image.asset_id,
                        "consent": image.consent_id,
                        "photo_type": image.photo_type,
                        "label": image.label,
                        "is_primary": image.is_primary,
                    }
                    for image in images
                ],
            )

    def active_for_account(self, account_id: UUID) -> PersonProfile | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        profile_id,
                        account_id,
                        principal_id,
                        person_asset_id,
                        consent_id,
                        height_cm,
                        weight_kg,
                        status,
                        last_used_at
                    FROM person_profiles
                    WHERE account_id = :account AND status = 'ACTIVE'
                    """
                ),
                {"account": account_id},
            ).one_or_none()
            if row is None:
                return None
            image_rows = connection.execute(
                text(
                    """
                    SELECT
                        profile_image_id,
                        asset_id,
                        consent_id,
                        photo_type,
                        label,
                        is_primary
                    FROM person_profile_images
                    WHERE profile_id = :profile AND account_id = :account
                    ORDER BY is_primary DESC, created_at, profile_image_id
                    """
                ),
                {"profile": row._mapping["profile_id"], "account": account_id},
            ).mappings()
            images = tuple(
                ProfileImage(
                    profile_image_id=image["profile_image_id"],
                    asset_id=image["asset_id"],
                    consent_id=image["consent_id"],
                    photo_type=image["photo_type"],
                    label=image["label"],
                    is_primary=image["is_primary"],
                )
                for image in image_rows
            )
        return _profile(row, images)

    def request_delete(self, profile_id: UUID, account_id: UUID, delete_after: datetime) -> bool:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    UPDATE person_profiles
                    SET status = 'DELETION_REQUESTED',
                        delete_after = :delete_after,
                        updated_at = now()
                    WHERE profile_id = :profile
                      AND account_id = :account
                      AND status = 'ACTIVE'
                    RETURNING profile_id, person_asset_id
                    """
                    ),
                    {
                        "profile": profile_id,
                        "account": account_id,
                        "delete_after": delete_after,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                connection.execute(
                    text(
                        """
                        UPDATE media_assets
                        SET deletion_state = 'REQUESTED',
                            delete_after = :delete_after,
                            updated_at = now()
                        WHERE account_id = :account
                          AND asset_id IN (
                              SELECT asset_id
                              FROM person_profile_images
                              WHERE profile_id = :profile AND account_id = :account
                              UNION
                              SELECT :legacy_asset
                          )
                        """
                    ),
                    {
                        "profile": row["profile_id"],
                        "legacy_asset": row["person_asset_id"],
                        "account": account_id,
                        "delete_after": delete_after,
                    },
                )
        return row is not None

    def restore_requested(self, account_id: UUID, restored_at: datetime) -> bool:
        """Restore a profile whose purge has not claimed or deleted any owned photo."""
        with self.engine.begin() as connection:
            profile = (
                connection.execute(
                    text(
                        """
                        SELECT profile_id, person_asset_id
                        FROM person_profiles requested
                        WHERE requested.account_id = :account
                          AND requested.status = 'DELETION_REQUESTED'
                          AND NOT EXISTS (
                              SELECT 1 FROM person_profiles active
                              WHERE active.account_id = requested.account_id
                                AND active.status = 'ACTIVE'
                          )
                        ORDER BY requested.updated_at DESC, requested.profile_id
                        FOR UPDATE OF requested
                        LIMIT 1
                        """
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if profile is None:
                return False
            media = tuple(
                connection.execute(
                    text(
                        """
                        SELECT asset_id, deletion_state
                        FROM media_assets
                        WHERE account_id = :account
                          AND asset_id IN (
                              SELECT asset_id FROM person_profile_images
                              WHERE profile_id = :profile AND account_id = :account
                              UNION
                              SELECT :legacy_asset
                          )
                        FOR UPDATE
                        """
                    ),
                    {
                        "account": account_id,
                        "profile": profile["profile_id"],
                        "legacy_asset": profile["person_asset_id"],
                    },
                ).mappings()
            )
            if not media or any(
                item["deletion_state"] not in {"RETAINED", "REQUESTED"} for item in media
            ):
                return False
            connection.execute(
                text(
                    """
                    UPDATE person_profiles
                    SET status = 'ACTIVE', delete_after = NULL, deleted_at = NULL,
                        updated_at = :restored_at
                    WHERE profile_id = :profile AND account_id = :account
                      AND status = 'DELETION_REQUESTED'
                    """
                ),
                {
                    "account": account_id,
                    "profile": profile["profile_id"],
                    "restored_at": restored_at,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE media_assets
                    SET deletion_state = 'RETAINED', delete_after = NULL, deleted_at = NULL,
                        updated_at = :restored_at
                    WHERE account_id = :account
                      AND asset_id IN (
                          SELECT asset_id FROM person_profile_images
                          WHERE profile_id = :profile AND account_id = :account
                          UNION
                          SELECT :legacy_asset
                      )
                      AND deletion_state IN ('RETAINED', 'REQUESTED')
                    """
                ),
                {
                    "account": account_id,
                    "profile": profile["profile_id"],
                    "legacy_asset": profile["person_asset_id"],
                    "restored_at": restored_at,
                },
            )
        return True


class PostgresConsentStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def asset_belongs_to(self, asset_id: UUID, account_id: UUID) -> bool:
        with self.engine.connect() as connection:
            owned = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM media_assets
                    WHERE asset_id = :asset
                      AND account_id = :account
                      AND purpose = 'PERSON_SOURCE'
                      AND deletion_state = 'RETAINED'
                    """
                ),
                {"asset": asset_id, "account": account_id},
            ).scalar_one_or_none()
        return owned is not None

    def append(self, evidence: ConsentEvidence) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO consent_records
                        (
                            consent_id,
                            account_id,
                            asset_id,
                            actor_principal_id,
                            consent_version,
                            purpose,
                            permission_asserted,
                            accepted_at,
                            withdrawn_at
                        )
                    VALUES
                        (
                            :consent,
                            :account,
                            :asset,
                            :principal,
                            :version,
                            :purpose,
                            true,
                            :accepted_at,
                            :withdrawn_at
                        )
                    """
                ),
                {
                    "consent": evidence.consent_id,
                    "account": evidence.account_id,
                    "asset": evidence.asset_id,
                    "principal": evidence.actor_principal_id,
                    "version": evidence.consent_version,
                    "purpose": evidence.purpose,
                    "accepted_at": evidence.accepted_at,
                    "withdrawn_at": evidence.withdrawn_at,
                },
            )

    def latest(
        self,
        account_id: UUID,
        actor_principal_id: UUID,
        asset_id: UUID,
        purpose: ConsentPurpose,
    ) -> ConsentEvidence | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT
                        consent_id,
                        account_id,
                        actor_principal_id,
                        asset_id,
                        purpose,
                        consent_version,
                        accepted_at,
                        withdrawn_at
                    FROM consent_records
                    WHERE account_id = :account
                      AND actor_principal_id = :principal
                      AND asset_id = :asset
                      AND purpose = :purpose
                    ORDER BY accepted_at DESC, created_at DESC
                    LIMIT 1
                    """
                    ),
                    {
                        "account": account_id,
                        "principal": actor_principal_id,
                        "asset": asset_id,
                        "purpose": purpose,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return ConsentEvidence(
            consent_id=row["consent_id"],
            account_id=row["account_id"],
            actor_principal_id=row["actor_principal_id"],
            asset_id=row["asset_id"],
            purpose=row["purpose"],
            consent_version=row["consent_version"],
            accepted_at=row["accepted_at"],
            withdrawn_at=row["withdrawn_at"],
        )


class PostgresQuotaStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _usage(row: object, account_id: UUID, usage_date: date) -> DailyUsage:
        if row is None:
            return DailyUsage(account_id, usage_date, 0, None)
        values = row._mapping  # type: ignore[attr-defined]
        return DailyUsage(
            account_id=values["account_id"],
            usage_date_ist=values["usage_date_ist"],
            successful_generations=values["successful_generations"],
            active_job_id=values["active_job_id"],
        )

    def get(self, account_id: UUID, usage_date: date) -> DailyUsage | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT account_id, usage_date_ist, successful_generations, active_job_id
                    FROM generation_daily_usage
                    WHERE account_id = :account AND usage_date_ist = :usage_date
                    """
                ),
                {"account": account_id, "usage_date": usage_date},
            ).one_or_none()
        return self._usage(row, account_id, usage_date) if row is not None else None

    def reserve(
        self, account_id: UUID, usage_date: date, job_id: UUID, maximum: int
    ) -> DailyUsage | None:
        return self._mutate(account_id, usage_date, job_id, maximum, "reserve")

    def settle_success(
        self, account_id: UUID, usage_date: date, job_id: UUID, maximum: int
    ) -> DailyUsage | None:
        return self._mutate(account_id, usage_date, job_id, maximum, "settle")

    def release(self, account_id: UUID, usage_date: date, job_id: UUID) -> DailyUsage | None:
        return self._mutate(account_id, usage_date, job_id, 3, "release")

    def _mutate(
        self,
        account_id: UUID,
        usage_date: date,
        job_id: UUID,
        maximum: int,
        action: str,
    ) -> DailyUsage | None:
        statements = {
            "reserve": """
                INSERT INTO generation_daily_usage
                    (account_id, usage_date_ist, active_job_id)
                VALUES (:account, :usage_date, :job)
                ON CONFLICT (account_id, usage_date_ist) DO UPDATE
                SET active_job_id = EXCLUDED.active_job_id, updated_at = now()
                WHERE generation_daily_usage.successful_generations < :maximum
                  AND generation_daily_usage.active_job_id IS NULL
                RETURNING account_id, usage_date_ist, successful_generations, active_job_id
            """,
            "settle": """
                UPDATE generation_daily_usage
                SET successful_generations = successful_generations + 1,
                    active_job_id = NULL,
                    updated_at = now()
                WHERE account_id = :account
                  AND usage_date_ist = :usage_date
                  AND active_job_id = :job
                  AND successful_generations < :maximum
                RETURNING account_id, usage_date_ist, successful_generations, active_job_id
            """,
            "release": """
                UPDATE generation_daily_usage
                SET active_job_id = NULL, updated_at = now()
                WHERE account_id = :account
                  AND usage_date_ist = :usage_date
                  AND active_job_id = :job
                RETURNING account_id, usage_date_ist, successful_generations, active_job_id
            """,
        }
        with self.engine.begin() as connection:
            row = connection.execute(
                text(statements[action]),
                {
                    "account": account_id,
                    "usage_date": usage_date,
                    "job": job_id,
                    "maximum": maximum,
                },
            ).one_or_none()
        return self._usage(row, account_id, usage_date) if row is not None else None


class PostgresQuoteStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, quote: BetaRenderQuote) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO render_quotes
                        (
                            quote_id,
                            account_id,
                            person_asset_id,
                            consent_id,
                            expires_at,
                            principal_id,
                            profile_id,
                            item_asset_id,
                            remaining_allowance,
                            provider,
                            model_version,
                            provider_region
                        )
                    SELECT
                        :quote,
                        profile.account_id,
                        :person_asset,
                        :consent,
                        :expires_at,
                        profile.principal_id,
                        profile.profile_id,
                        :item_asset,
                        :remaining,
                        :provider,
                        :model,
                        :region
                    FROM person_profiles AS profile
                    WHERE profile.profile_id = :profile
                      AND profile.account_id = :account
                      AND profile.principal_id = :principal
                      AND profile.status = 'ACTIVE'
                      AND (
                          EXISTS (
                              SELECT 1
                              FROM person_profile_images AS image
                              WHERE image.profile_id = profile.profile_id
                                AND image.account_id = profile.account_id
                                AND image.asset_id = :person_asset
                                AND image.consent_id = :consent
                          )
                          OR (
                              profile.person_asset_id = :person_asset
                              AND profile.consent_id = :consent
                          )
                      )
                    """
                ),
                {
                    "quote": quote.quote_id,
                    "expires_at": quote.expires_at,
                    "item_asset": quote.item_asset_id,
                    "person_asset": quote.person_asset_id,
                    "consent": quote.consent_id,
                    "remaining": quote.remaining_before,
                    "provider": quote.route.provider,
                    "model": quote.route.model,
                    "region": quote.route.region,
                    "profile": quote.profile_id,
                    "account": quote.account_id,
                    "principal": quote.principal_id,
                },
            )


def decimal_or_none(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
