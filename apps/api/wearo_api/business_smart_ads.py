from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote, urlencode, urljoin
from uuid import UUID, uuid4

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Connection, Engine, text

from .image_watermark import apply_generated_image_watermark
from .media_runtime import PostgresMediaRuntime
from .retention import RetentionService
from .tenant_scope import TenantScopeError, require_tenant_scope

MAX_DAILY_GENERATIONS = 2
CREATIVE_WIDTH = 768
CREATIVE_HEIGHT = 1024
TargetGender = Literal["all", "female", "male", "non_binary"]
DeliveryChannel = Literal["EMAIL", "WHATSAPP"]


class SmartAdError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def smart_ad_try_on_url(
    public_origin: str,
    business_reference: str,
    public_key: str,
    campaign_token: UUID,
) -> str:
    shop_url = urljoin(
        public_origin.rstrip("/") + "/",
        f"shop/{quote(business_reference, safe='')}",
    )
    return f"{shop_url}?{urlencode({'key': public_key, 'smart_ad': str(campaign_token)})}"


def normalize_creative(content: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(
                image,
                (CREATIVE_WIDTH, CREATIVE_HEIGHT),
                Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            image.save(output, "JPEG", quality=90, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise SmartAdError(
            "INVALID_SMART_AD_IMAGE", "Upload a valid JPEG, PNG, or WebP image."
        ) from None


class OpenAISmartAdGenerator:
    endpoint = "https://api.openai.com/v1/images/edits"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @staticmethod
    def _data_url(content: bytes, content_type: str) -> str:
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    def generate(
        self,
        prompt: str,
        jewellery: tuple[bytes, str],
        model_photo: tuple[bytes, str] | None,
        *,
        safety_identifier: str,
    ) -> bytes:
        if not self.api_key or not self.model:
            raise SmartAdError("SMART_AD_AI_UNAVAILABLE", "SmartAds generation is not configured.")
        images = [
            {"image_url": self._data_url(jewellery[0], jewellery[1])},
        ]
        if model_photo is not None:
            images.append({"image_url": self._data_url(model_photo[0], model_photo[1])})
        creative_prompt = (
            "Create a premium portrait jewellery advertisement concept. Preserve the exact "
            "jewellery design, materials, stones, and proportions from the first reference. "
            "If a second reference is present, use that model and preserve their appearance. "
            "Use tasteful commercial lighting and composition. Do not add logos, prices, "
            "claims, or small print. Campaign direction: "
            f"{prompt}"
        )
        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "images": images,
                "prompt": creative_prompt,
                "size": "1024x1536",
                "quality": "high",
                "output_format": "png",
                "n": 1,
                "safety_identifier": safety_identifier[:128],
            },
            timeout=180,
        )
        if response.status_code != 200:
            raise SmartAdError(
                "SMART_AD_AI_FAILED", "The advertisement concept could not be generated."
            )
        try:
            return base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
        except (KeyError, IndexError, TypeError, ValueError, requests.JSONDecodeError):
            raise SmartAdError(
                "SMART_AD_AI_FAILED", "The advertisement concept response was invalid."
            ) from None


class PostgresBusinessSmartAds:
    def __init__(
        self,
        engine: Engine,
        media: PostgresMediaRuntime,
        generator: OpenAISmartAdGenerator,
        retention: RetentionService,
    ) -> None:
        self.engine = engine
        self.media = media
        self.generator = generator
        self.retention = retention

    @staticmethod
    def _owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise SmartAdError("SMART_AD_UNAVAILABLE", "SmartAds resource unavailable.") from None

    @staticmethod
    def _details(title: str, prompt: str) -> tuple[str, str]:
        clean_title, clean_prompt = title.strip(), prompt.strip()
        if not clean_title or len(clean_title) > 120 or "\r" in clean_title or "\n" in clean_title:
            raise SmartAdError(
                "INVALID_SMART_AD_TITLE", "Enter an advertisement title under 120 characters."
            )
        if not clean_prompt or len(clean_prompt) > 2000:
            raise SmartAdError(
                "INVALID_SMART_AD_PROMPT", "Enter a generation prompt under 2,000 characters."
            )
        return clean_title, clean_prompt

    @staticmethod
    def _remaining(attempts: int) -> int:
        return max(MAX_DAILY_GENERATIONS - attempts, 0)

    @staticmethod
    def _schedule_details(
        occasion: str,
        scheduled_for: datetime,
        channel: DeliveryChannel,
        target_age_min: int | None,
        target_age_max: int | None,
    ) -> tuple[str, datetime]:
        clean_occasion = occasion.strip()
        if (
            not clean_occasion
            or len(clean_occasion) > 160
            or "\r" in clean_occasion
            or "\n" in clean_occasion
        ):
            raise SmartAdError(
                "INVALID_SMART_AD_OCCASION", "Enter an occasion under 160 characters."
            )
        if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
            raise SmartAdError("INVALID_SMART_AD_TIME", "Choose a time with a timezone.")
        scheduled_utc = scheduled_for.astimezone(UTC)
        if scheduled_utc <= datetime.now(UTC):
            raise SmartAdError("INVALID_SMART_AD_TIME", "Choose a future delivery time.")
        if channel != "EMAIL":
            raise SmartAdError(
                "SMART_AD_CHANNEL_UNAVAILABLE", "WhatsApp delivery is not available yet."
            )
        if target_age_min is not None and not 1 <= target_age_min <= 120:
            raise SmartAdError("INVALID_SMART_AD_AGE", "Minimum age must be from 1 to 120.")
        if target_age_max is not None and not 1 <= target_age_max <= 120:
            raise SmartAdError("INVALID_SMART_AD_AGE", "Maximum age must be from 1 to 120.")
        if (
            target_age_min is not None
            and target_age_max is not None
            and target_age_min > target_age_max
        ):
            raise SmartAdError("INVALID_SMART_AD_AGE", "Minimum age cannot exceed maximum age.")
        return clean_occasion, scheduled_utc

    def list(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            parameters = {"tenant": tenant_id, "account": account_id}
            female_users = int(
                connection.execute(
                    text(
                        """SELECT count(DISTINCT person.person_id)
                        FROM account_persons person
                        JOIN person_tryon_observations observation
                          ON observation.person_id=person.person_id
                         AND observation.account_id=person.account_id
                        WHERE observation.tenant_id=:tenant
                          AND observation.business_account_id=:account
                          AND person.gender='female'"""
                    ),
                    parameters,
                ).scalar_one()
            )
            eligible_female_users = int(
                connection.execute(
                    text(
                        """SELECT count(DISTINCT person.person_id)
                        FROM account_persons person
                        JOIN person_tryon_observations observation
                          ON observation.person_id=person.person_id
                         AND observation.account_id=person.account_id
                        WHERE observation.tenant_id=:tenant
                          AND observation.business_account_id=:account
                          AND person.gender='female'
                          AND observation.marketing_eligible=true"""
                    ),
                    parameters,
                ).scalar_one()
            )
            attempts_today = int(
                connection.execute(
                    text(
                        """SELECT count(*) FROM business_smart_ad_generations
                        WHERE tenant_id=:tenant AND account_id=:account
                          AND (generated_at AT TIME ZONE 'Asia/Kolkata')::date =
                              (now() AT TIME ZONE 'Asia/Kolkata')::date"""
                    ),
                    parameters,
                ).scalar_one()
            )
            generation_in_progress = bool(
                connection.execute(
                    text(
                        """SELECT EXISTS(
                            SELECT 1 FROM business_smart_ad_generations
                            WHERE tenant_id=:tenant AND account_id=:account
                              AND status='RESERVED'
                              AND updated_at >= now() - interval '10 minutes'
                        )"""
                    ),
                    parameters,
                ).scalar_one()
            )
            ads = [
                dict(row)
                for row in connection.execute(
                    text(
                        """SELECT smart_ad_id,title,prompt,jewellery_asset_id,model_asset_id,
                                  creative_asset_id,status,accepted_at,created_at,updated_at
                        FROM business_smart_ads
                        WHERE tenant_id=:tenant AND account_id=:account
                        ORDER BY updated_at DESC"""
                    ),
                    parameters,
                ).mappings()
            ]
            schedules = [
                dict(row)
                for row in connection.execute(
                    text(
                        """SELECT schedule.schedule_id,schedule.smart_ad_id,ad.title,
                                  schedule.occasion,schedule.channel,schedule.scheduled_for,
                                  schedule.target_gender,schedule.target_age_min,
                                  schedule.target_age_max,schedule.target_user_count,
                                  schedule.queued_recipient_count,schedule.created_at,
                                  count(job.job_id) FILTER (WHERE job.status='DELIVERED') delivered,
                                  count(job.job_id) FILTER (WHERE job.status='FAILED') failed,
                                  count(job.job_id) FILTER
                                    (WHERE job.status IN ('QUEUED','RETRY')) pending,
                                  count(job.job_id) FILTER
                                    (WHERE job.status='PROCESSING') processing
                        FROM business_smart_ad_schedules schedule
                        JOIN business_smart_ads ad ON ad.smart_ad_id=schedule.smart_ad_id
                        LEFT JOIN communication_jobs job
                          ON job.metadata->>'smart_ad_schedule_id'=schedule.schedule_id::text
                        WHERE schedule.tenant_id=:tenant AND schedule.account_id=:account
                        GROUP BY schedule.schedule_id,ad.title
                        ORDER BY schedule.scheduled_for DESC"""
                    ),
                    parameters,
                ).mappings()
            ]
            for schedule in schedules:
                schedule["can_edit"] = bool(
                    int(schedule["delivered"]) == 0
                    and int(schedule["processing"]) == 0
                    and schedule["scheduled_for"] > datetime.now(UTC)
                )
                schedule["can_delete"] = bool(
                    int(schedule["delivered"]) == 0 and int(schedule["processing"]) == 0
                )
        return {
            "female_unique_users": female_users,
            "female_marketing_eligible_users": eligible_female_users,
            "attempts_used_today": attempts_today,
            "attempts_remaining_today": self._remaining(attempts_today),
            "maximum_daily_attempts": MAX_DAILY_GENERATIONS,
            "generation_in_progress": generation_in_progress,
            "items": ads,
            "schedules": schedules,
        }

    def create(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        *,
        title: str,
        prompt: str,
        jewellery: bytes,
        jewellery_type: str,
        model_photo: bytes | None,
        model_type: str | None,
    ) -> dict[str, object]:
        clean_title, clean_prompt = self._details(title, prompt)
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
        jewellery_asset = self.media.store_smart_ad(account_id, jewellery, jewellery_type)
        try:
            model_asset = (
                self.media.store_smart_ad(account_id, model_photo, model_type or "")
                if model_photo
                else None
            )
        except Exception:
            self.retention.request_delete(jewellery_asset.asset_id, account_id)
            raise
        try:
            with self.engine.begin() as connection:
                row = (
                    connection.execute(
                        text(
                            """INSERT INTO business_smart_ads
                            (tenant_id,account_id,title,prompt,jewellery_asset_id,model_asset_id)
                            VALUES (:tenant,:account,:title,:prompt,:jewellery,:model)
                            RETURNING smart_ad_id,title,prompt,jewellery_asset_id,model_asset_id,
                                      creative_asset_id,status,accepted_at,created_at,updated_at"""
                        ),
                        {
                            "tenant": tenant_id,
                            "account": account_id,
                            "title": clean_title,
                            "prompt": clean_prompt,
                            "jewellery": jewellery_asset.asset_id,
                            "model": model_asset.asset_id if model_asset else None,
                        },
                    )
                    .mappings()
                    .one()
                )
            return dict(row)
        except Exception:
            self.retention.request_delete(jewellery_asset.asset_id, account_id)
            if model_asset:
                self.retention.request_delete(model_asset.asset_id, account_id)
            raise

    def generate(self, principal_id: UUID, tenant_id: UUID, smart_ad_id: UUID) -> dict[str, object]:
        generation_id = uuid4()
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            connection.execute(
                text(
                    """SELECT tenant_id FROM business_tenants
                    WHERE tenant_id=:tenant AND account_id=:account FOR UPDATE"""
                ),
                {"tenant": tenant_id, "account": account_id},
            ).one()
            ad = (
                connection.execute(
                    text(
                        """SELECT ad.smart_ad_id,ad.title,ad.prompt,ad.jewellery_asset_id,
                                  ad.model_asset_id,ad.status,profile.logo_asset_id
                        FROM business_smart_ads ad
                        JOIN business_profiles profile
                          ON profile.tenant_id=ad.tenant_id
                         AND profile.account_id=ad.account_id
                        WHERE ad.smart_ad_id=:ad AND ad.tenant_id=:tenant
                          AND ad.account_id=:account"""
                    ),
                    {"ad": smart_ad_id, "tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if ad is None:
                raise SmartAdError("SMART_AD_UNAVAILABLE", "SmartAds resource unavailable.")
            if ad["status"] == "ACTIVE":
                raise SmartAdError(
                    "SMART_AD_ALREADY_ACTIVE", "An accepted advertisement cannot be regenerated."
                )
            if ad["logo_asset_id"] is None:
                raise SmartAdError(
                    "SMART_AD_BUSINESS_LOGO_REQUIRED",
                    "Upload a company logo before generating a SmartAds advertisement.",
                )
            connection.execute(
                text(
                    """UPDATE business_smart_ad_generations
                    SET status='FAILED',failure_code='GENERATION_TIMEOUT',updated_at=now()
                    WHERE tenant_id=:tenant AND account_id=:account
                      AND status='RESERVED'
                      AND updated_at < now() - interval '10 minutes'"""
                ),
                {"tenant": tenant_id, "account": account_id},
            )
            generation_in_progress = bool(
                connection.execute(
                    text(
                        """SELECT EXISTS(
                            SELECT 1 FROM business_smart_ad_generations
                            WHERE tenant_id=:tenant AND account_id=:account
                              AND status='RESERVED'
                        )"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                ).scalar_one()
            )
            if generation_in_progress:
                raise SmartAdError(
                    "SMART_AD_GENERATION_IN_PROGRESS",
                    "Another advertisement concept is still generating. Wait for it to finish.",
                )
            attempts = int(
                connection.execute(
                    text(
                        """SELECT count(*) FROM business_smart_ad_generations
                        WHERE tenant_id=:tenant AND account_id=:account
                          AND (generated_at AT TIME ZONE 'Asia/Kolkata')::date =
                              (now() AT TIME ZONE 'Asia/Kolkata')::date"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                ).scalar_one()
            )
            if attempts >= MAX_DAILY_GENERATIONS:
                raise SmartAdError(
                    "SMART_AD_DAILY_LIMIT_REACHED",
                    "Both SmartAds generation tries have been used for today.",
                )
            connection.execute(
                text(
                    """INSERT INTO business_smart_ad_generations
                    (generation_id,smart_ad_id,tenant_id,account_id,status)
                    VALUES (:generation,:ad,:tenant,:account,'RESERVED')"""
                ),
                {
                    "generation": generation_id,
                    "ad": smart_ad_id,
                    "tenant": tenant_id,
                    "account": account_id,
                },
            )
        try:
            jewellery = self.media.read_owned(ad["jewellery_asset_id"], account_id)
            model_photo = (
                self.media.read_owned(ad["model_asset_id"], account_id)
                if ad["model_asset_id"]
                else None
            )
            business_logo, _ = self.media.read_owned(ad["logo_asset_id"], account_id)
            stable_identifier = hashlib.sha256(f"{account_id}:{tenant_id}".encode()).hexdigest()
            creative = normalize_creative(
                self.generator.generate(
                    str(ad["prompt"]),
                    jewellery,
                    model_photo,
                    safety_identifier=stable_identifier,
                )
            )
            creative, _ = apply_generated_image_watermark(
                creative,
                "image/jpeg",
                company_logo=business_logo,
            )
            asset = self.media.store_smart_ad(account_id, creative, "image/jpeg")
        except Exception as error:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """UPDATE business_smart_ad_generations
                        SET status='FAILED',failure_code=:code,updated_at=now()
                        WHERE generation_id=:generation"""
                    ),
                    {"generation": generation_id, "code": type(error).__name__[:100]},
                )
            raise
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """UPDATE business_smart_ads SET creative_asset_id=:asset,updated_at=now()
                        WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                        RETURNING smart_ad_id,title,prompt,jewellery_asset_id,model_asset_id,
                                  creative_asset_id,status,accepted_at,created_at,updated_at"""
                    ),
                    {
                        "asset": asset.asset_id,
                        "ad": smart_ad_id,
                        "tenant": tenant_id,
                        "account": account_id,
                    },
                )
                .mappings()
                .one()
            )
            connection.execute(
                text(
                    """UPDATE business_smart_ad_generations
                    SET status='COMPLETE',generated_asset_id=:asset,updated_at=now()
                    WHERE generation_id=:generation"""
                ),
                {"generation": generation_id, "asset": asset.asset_id},
            )
            attempts = int(
                connection.execute(
                    text(
                        """SELECT count(*) FROM business_smart_ad_generations
                        WHERE tenant_id=:tenant AND account_id=:account
                          AND (generated_at AT TIME ZONE 'Asia/Kolkata')::date =
                              (now() AT TIME ZONE 'Asia/Kolkata')::date"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                ).scalar_one()
            )
        return {**dict(row), "attempts_remaining_today": self._remaining(attempts)}

    def update(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        smart_ad_id: UUID,
        *,
        title: str,
        prompt: str,
    ) -> dict[str, object]:
        clean_title, clean_prompt = self._details(title, prompt)
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            row = (
                connection.execute(
                    text(
                        """UPDATE business_smart_ads
                        SET title=:title,prompt=:prompt,updated_at=now()
                        WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                        RETURNING smart_ad_id,title,prompt,jewellery_asset_id,model_asset_id,
                                  creative_asset_id,status,accepted_at,created_at,updated_at"""
                    ),
                    {
                        "title": clean_title,
                        "prompt": clean_prompt,
                        "ad": smart_ad_id,
                        "tenant": tenant_id,
                        "account": account_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SmartAdError("SMART_AD_UNAVAILABLE", "SmartAds resource unavailable.")
        return dict(row)

    def accept(self, principal_id: UUID, tenant_id: UUID, smart_ad_id: UUID) -> dict[str, object]:
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            row = (
                connection.execute(
                    text(
                        """UPDATE business_smart_ads
                        SET status='ACTIVE',accepted_at=COALESCE(accepted_at,now()),updated_at=now()
                        WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                          AND creative_asset_id IS NOT NULL
                        RETURNING smart_ad_id,title,prompt,jewellery_asset_id,model_asset_id,
                                  creative_asset_id,status,accepted_at,created_at,updated_at"""
                    ),
                    {"ad": smart_ad_id, "tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SmartAdError(
                "SMART_AD_CREATIVE_REQUIRED",
                "Generate a concept before accepting the advertisement.",
            )
        return dict(row)

    def delete(self, principal_id: UUID, tenant_id: UUID, smart_ad_id: UUID) -> None:
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            asset_ids = {
                row[0]
                for row in connection.execute(
                    text(
                        """SELECT asset_id FROM (
                          SELECT jewellery_asset_id AS asset_id FROM business_smart_ads
                          WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                          UNION SELECT model_asset_id FROM business_smart_ads
                          WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                          UNION SELECT creative_asset_id FROM business_smart_ads
                          WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                          UNION SELECT generated_asset_id FROM business_smart_ad_generations
                          WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                        ) assets WHERE asset_id IS NOT NULL"""
                    ),
                    {"ad": smart_ad_id, "tenant": tenant_id, "account": account_id},
                )
            }
            connection.execute(
                text(
                    """UPDATE communication_jobs
                    SET status='CANCELLED',last_error_code='SMART_AD_DELETED',updated_at=now()
                    WHERE metadata->>'smart_ad_id'=:ad
                      AND status IN ('QUEUED','RETRY')"""
                ),
                {"ad": str(smart_ad_id)},
            )
            removed = connection.execute(
                text(
                    """DELETE FROM business_smart_ads
                    WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account
                    RETURNING smart_ad_id"""
                ),
                {"ad": smart_ad_id, "tenant": tenant_id, "account": account_id},
            ).scalar_one_or_none()
        if removed is None:
            raise SmartAdError("SMART_AD_UNAVAILABLE", "SmartAds resource unavailable.")
        for asset_id in asset_ids:
            self.retention.request_delete(asset_id, account_id)

    def image(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        smart_ad_id: UUID,
        role: Literal["jewellery", "model", "creative"],
    ) -> tuple[bytes, str]:
        column = {
            "jewellery": "jewellery_asset_id",
            "model": "model_asset_id",
            "creative": "creative_asset_id",
        }[role]
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            asset_id = connection.execute(
                text(
                    f"""SELECT {column} FROM business_smart_ads
                    WHERE smart_ad_id=:ad AND tenant_id=:tenant AND account_id=:account"""  # noqa: S608
                ),
                {"ad": smart_ad_id, "tenant": tenant_id, "account": account_id},
            ).scalar_one_or_none()
        if asset_id is None:
            raise SmartAdError("SMART_AD_IMAGE_UNAVAILABLE", "SmartAds image unavailable.")
        return self.media.read_owned(asset_id, account_id)

    def public_image(self, token: UUID) -> tuple[bytes, str]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT ad.creative_asset_id,ad.account_id
                        FROM business_smart_ad_schedules schedule
                        JOIN business_smart_ads ad ON ad.smart_ad_id=schedule.smart_ad_id
                         AND ad.account_id=schedule.account_id
                        WHERE schedule.public_token=:token AND ad.status='ACTIVE'"""
                    ),
                    {"token": token},
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["creative_asset_id"] is None:
            raise SmartAdError("SMART_AD_IMAGE_UNAVAILABLE", "SmartAds image unavailable.")
        return self.media.read_owned(row["creative_asset_id"], row["account_id"])

    def public_try_on_item(self, token: UUID) -> tuple[bytes, str]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT ad.jewellery_asset_id,ad.account_id
                        FROM business_smart_ad_schedules schedule
                        JOIN business_smart_ads ad ON ad.smart_ad_id=schedule.smart_ad_id
                         AND ad.account_id=schedule.account_id
                        WHERE schedule.public_token=:token AND ad.status='ACTIVE'"""
                    ),
                    {"token": token},
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["jewellery_asset_id"] is None:
            raise SmartAdError("SMART_AD_IMAGE_UNAVAILABLE", "SmartAds item unavailable.")
        return self.media.read_owned(row["jewellery_asset_id"], row["account_id"])

    def schedule(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        smart_ad_id: UUID,
        *,
        occasion: str,
        scheduled_for: datetime,
        channel: DeliveryChannel,
        target_gender: TargetGender,
        target_age_min: int | None,
        target_age_max: int | None,
        public_origin: str,
    ) -> dict[str, object]:
        clean_occasion, scheduled_utc = self._schedule_details(
            occasion,
            scheduled_for,
            channel,
            target_age_min,
            target_age_max,
        )
        schedule_id, public_token = uuid4(), uuid4()
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            ad = (
                connection.execute(
                    text(
                        """SELECT ad.title,profile.display_name,tenant.slug business_reference,
                                  shop.public_code
                        FROM business_smart_ads ad
                        JOIN business_profiles profile ON profile.tenant_id=ad.tenant_id
                         AND profile.account_id=ad.account_id
                        JOIN business_tenants tenant ON tenant.tenant_id=ad.tenant_id
                         AND tenant.account_id=ad.account_id
                        JOIN business_shop_links shop ON shop.tenant_id=ad.tenant_id
                         AND shop.account_id=ad.account_id
                        WHERE ad.smart_ad_id=:ad AND ad.tenant_id=:tenant
                          AND ad.account_id=:account AND ad.status='ACTIVE'
                          AND shop.enabled AND tenant.status='ACTIVE'"""
                    ),
                    {"ad": smart_ad_id, "tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if ad is None:
                raise SmartAdError(
                    "SMART_AD_NOT_ACTIVE", "Accept the advertisement before scheduling it."
                )
            audience = list(
                connection.execute(
                    text(
                        """SELECT DISTINCT person.person_id,person.account_id,
                               COALESCE(participant.normalized_email,email.normalized_value) email
                        FROM account_persons person
                        JOIN person_tryon_observations observation
                          ON observation.person_id=person.person_id
                         AND observation.account_id=person.account_id
                        JOIN business_participants participant
                          ON participant.consumer_account_id=person.account_id
                         AND participant.tenant_id=:tenant
                         AND participant.business_account_id=:account
                        LEFT JOIN LATERAL (
                          SELECT identity.normalized_value
                          FROM principal_identities identity
                          WHERE identity.account_id=person.account_id
                            AND identity.channel='EMAIL' AND identity.verified_at IS NOT NULL
                          ORDER BY identity.verified_at DESC LIMIT 1
                        ) email ON true
                        WHERE observation.tenant_id=:tenant
                          AND observation.business_account_id=:account
                          AND observation.marketing_eligible=true
                          AND (:gender='all' OR person.gender=:gender)
                          AND (CAST(:age_min AS smallint) IS NULL
                               OR person.estimated_age >= :age_min)
                          AND (CAST(:age_max AS smallint) IS NULL
                               OR person.estimated_age <= :age_max)"""
                    ),
                    {
                        "tenant": tenant_id,
                        "account": account_id,
                        "gender": target_gender,
                        "age_min": target_age_min,
                        "age_max": target_age_max,
                    },
                ).mappings()
            )
            recipients = sorted({str(row["email"]) for row in audience if row["email"]})
            connection.execute(
                text(
                    """INSERT INTO business_smart_ad_schedules
                    (schedule_id,smart_ad_id,tenant_id,account_id,occasion,channel,scheduled_for,
                     target_gender,target_age_min,target_age_max,target_user_count,
                     queued_recipient_count,public_token)
                    VALUES (:schedule,:ad,:tenant,:account,:occasion,:channel,:scheduled,
                            :gender,:age_min,:age_max,:users,:recipients,:token)"""
                ),
                {
                    "schedule": schedule_id,
                    "ad": smart_ad_id,
                    "tenant": tenant_id,
                    "account": account_id,
                    "occasion": clean_occasion,
                    "channel": channel,
                    "scheduled": scheduled_utc,
                    "gender": target_gender,
                    "age_min": target_age_min,
                    "age_max": target_age_max,
                    "users": len(audience),
                    "recipients": len(recipients),
                    "token": public_token,
                },
            )
            image_url = urljoin(
                public_origin.rstrip("/") + "/",
                f"api/v1/public/smart-ads/{public_token}/image",
            )
            try_on_url = smart_ad_try_on_url(
                public_origin,
                str(ad["business_reference"]),
                str(ad["public_code"]),
                public_token,
            )
            if recipients:
                jobs = [
                    {
                        "job": uuid4(),
                        "recipient": recipient,
                        "variables": json.dumps(
                            {
                                "advertisement_title": str(ad["title"]),
                                "business_name": str(ad["display_name"]),
                                "occasion": clean_occasion,
                                "smart_ad_image_url": image_url,
                                "smart_ad_try_on_url": try_on_url,
                            }
                        ),
                        "metadata": json.dumps(
                            {
                                "smart_ad_id": str(smart_ad_id),
                                "smart_ad_schedule_id": str(schedule_id),
                            }
                        ),
                        "dedupe": f"smart-ad:{schedule_id}:{recipient}",
                        "scheduled": scheduled_utc,
                    }
                    for recipient in recipients
                ]
                connection.execute(
                    text(
                        """INSERT INTO communication_jobs
                        (job_id,channel,template_key,recipient,variables,metadata,
                         deduplication_key,scheduled_at,created_at,updated_at)
                        VALUES (:job,'EMAIL','SMART_AD',:recipient,CAST(:variables AS jsonb),
                                CAST(:metadata AS jsonb),:dedupe,:scheduled,now(),now())"""
                    ),
                    jobs,
                )
        return {
            "schedule_id": schedule_id,
            "smart_ad_id": smart_ad_id,
            "occasion": clean_occasion,
            "channel": channel,
            "scheduled_for": scheduled_utc,
            "target_gender": target_gender,
            "target_age_min": target_age_min,
            "target_age_max": target_age_max,
            "target_user_count": len(audience),
            "queued_recipient_count": len(recipients),
        }

    def update_schedule(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        schedule_id: UUID,
        smart_ad_id: UUID,
        *,
        occasion: str,
        scheduled_for: datetime,
        channel: DeliveryChannel,
        target_gender: TargetGender,
        target_age_min: int | None,
        target_age_max: int | None,
        public_origin: str,
    ) -> dict[str, object]:
        clean_occasion, scheduled_utc = self._schedule_details(
            occasion,
            scheduled_for,
            channel,
            target_age_min,
            target_age_max,
        )
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            schedule = (
                connection.execute(
                    text(
                        """SELECT public_token FROM business_smart_ad_schedules
                        WHERE schedule_id=:schedule AND tenant_id=:tenant
                          AND account_id=:account FOR UPDATE"""
                    ),
                    {"schedule": schedule_id, "tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if schedule is None:
                raise SmartAdError(
                    "SMART_AD_UNAVAILABLE", "Scheduled advertisement is unavailable."
                )
            locked_jobs = int(
                connection.execute(
                    text(
                        """SELECT count(*) FROM communication_jobs
                        WHERE metadata->>'smart_ad_schedule_id'=:schedule
                          AND status IN ('PROCESSING','DELIVERED')"""
                    ),
                    {"schedule": str(schedule_id)},
                ).scalar_one()
            )
            if locked_jobs:
                raise SmartAdError(
                    "SMART_AD_SCHEDULE_LOCKED",
                    "A campaign that is sending or already delivered cannot be modified.",
                )
            ad = (
                connection.execute(
                    text(
                        """SELECT ad.title,profile.display_name,tenant.slug business_reference,
                                  shop.public_code
                        FROM business_smart_ads ad
                        JOIN business_profiles profile ON profile.tenant_id=ad.tenant_id
                         AND profile.account_id=ad.account_id
                        JOIN business_tenants tenant ON tenant.tenant_id=ad.tenant_id
                         AND tenant.account_id=ad.account_id
                        JOIN business_shop_links shop ON shop.tenant_id=ad.tenant_id
                         AND shop.account_id=ad.account_id
                        WHERE ad.smart_ad_id=:ad AND ad.tenant_id=:tenant
                          AND ad.account_id=:account AND ad.status='ACTIVE'
                          AND shop.enabled AND tenant.status='ACTIVE'"""
                    ),
                    {"ad": smart_ad_id, "tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if ad is None:
                raise SmartAdError(
                    "SMART_AD_NOT_ACTIVE", "Choose an accepted advertisement."
                )
            audience = list(
                connection.execute(
                    text(
                        """SELECT DISTINCT person.person_id,person.account_id,
                               COALESCE(participant.normalized_email,email.normalized_value) email
                        FROM account_persons person
                        JOIN person_tryon_observations observation
                          ON observation.person_id=person.person_id
                         AND observation.account_id=person.account_id
                        JOIN business_participants participant
                          ON participant.consumer_account_id=person.account_id
                         AND participant.tenant_id=:tenant
                         AND participant.business_account_id=:account
                        LEFT JOIN LATERAL (
                          SELECT identity.normalized_value
                          FROM principal_identities identity
                          WHERE identity.account_id=person.account_id
                            AND identity.channel='EMAIL' AND identity.verified_at IS NOT NULL
                          ORDER BY identity.verified_at DESC LIMIT 1
                        ) email ON true
                        WHERE observation.tenant_id=:tenant
                          AND observation.business_account_id=:account
                          AND observation.marketing_eligible=true
                          AND (:gender='all' OR person.gender=:gender)
                          AND (CAST(:age_min AS smallint) IS NULL
                               OR person.estimated_age >= :age_min)
                          AND (CAST(:age_max AS smallint) IS NULL
                               OR person.estimated_age <= :age_max)"""
                    ),
                    {
                        "tenant": tenant_id,
                        "account": account_id,
                        "gender": target_gender,
                        "age_min": target_age_min,
                        "age_max": target_age_max,
                    },
                ).mappings()
            )
            recipients = sorted({str(row["email"]) for row in audience if row["email"]})
            current_jobs = {
                str(row["recipient"]): row
                for row in connection.execute(
                    text(
                        """SELECT job_id,recipient FROM communication_jobs
                        WHERE metadata->>'smart_ad_schedule_id'=:schedule
                          AND status IN ('QUEUED','RETRY') FOR UPDATE"""
                    ),
                    {"schedule": str(schedule_id)},
                ).mappings()
            }
            public_token = UUID(str(schedule["public_token"]))
            image_url = urljoin(
                public_origin.rstrip("/") + "/",
                f"api/v1/public/smart-ads/{public_token}/image",
            )
            try_on_url = smart_ad_try_on_url(
                public_origin,
                str(ad["business_reference"]),
                str(ad["public_code"]),
                public_token,
            )
            variables = json.dumps(
                {
                    "advertisement_title": str(ad["title"]),
                    "business_name": str(ad["display_name"]),
                    "occasion": clean_occasion,
                    "smart_ad_image_url": image_url,
                    "smart_ad_try_on_url": try_on_url,
                }
            )
            metadata = json.dumps(
                {
                    "smart_ad_id": str(smart_ad_id),
                    "smart_ad_schedule_id": str(schedule_id),
                }
            )
            retained = set(recipients).intersection(current_jobs)
            removed = set(current_jobs).difference(recipients)
            if retained:
                connection.execute(
                    text(
                        """UPDATE communication_jobs
                        SET variables=CAST(:variables AS jsonb),metadata=CAST(:metadata AS jsonb),
                            scheduled_at=:scheduled,status='QUEUED',attempt_count=0,
                            leased_by=NULL,lease_expires_at=NULL,last_error_code=NULL,
                            updated_at=now()
                        WHERE job_id=:job"""
                    ),
                    [
                        {
                            "variables": variables,
                            "metadata": metadata,
                            "scheduled": scheduled_utc,
                            "job": current_jobs[recipient]["job_id"],
                        }
                        for recipient in retained
                    ],
                )
            if removed:
                connection.execute(
                    text(
                        """UPDATE communication_jobs
                        SET status='CANCELLED',last_error_code='SMART_AD_SCHEDULE_UPDATED',
                            updated_at=now()
                        WHERE job_id=:job"""
                    ),
                    [{"job": current_jobs[recipient]["job_id"]} for recipient in removed],
                )
            added = [recipient for recipient in recipients if recipient not in current_jobs]
            if added:
                jobs = []
                for recipient in added:
                    job_id = uuid4()
                    jobs.append(
                        {
                            "job": job_id,
                            "recipient": recipient,
                            "variables": variables,
                            "metadata": metadata,
                            "dedupe": f"smart-ad:{schedule_id}:{recipient}:edit:{job_id}",
                            "scheduled": scheduled_utc,
                        }
                    )
                connection.execute(
                    text(
                        """INSERT INTO communication_jobs
                        (job_id,channel,template_key,recipient,variables,metadata,
                         deduplication_key,scheduled_at,created_at,updated_at)
                        VALUES (:job,'EMAIL','SMART_AD',:recipient,CAST(:variables AS jsonb),
                                CAST(:metadata AS jsonb),:dedupe,:scheduled,now(),now())"""
                    ),
                    jobs,
                )
            connection.execute(
                text(
                    """UPDATE business_smart_ad_schedules
                    SET smart_ad_id=:ad,occasion=:occasion,channel=:channel,
                        scheduled_for=:scheduled,target_gender=:gender,
                        target_age_min=:age_min,target_age_max=:age_max,
                        target_user_count=:users,queued_recipient_count=:recipients,
                        updated_at=now()
                    WHERE schedule_id=:schedule AND tenant_id=:tenant AND account_id=:account"""
                ),
                {
                    "schedule": schedule_id,
                    "ad": smart_ad_id,
                    "tenant": tenant_id,
                    "account": account_id,
                    "occasion": clean_occasion,
                    "channel": channel,
                    "scheduled": scheduled_utc,
                    "gender": target_gender,
                    "age_min": target_age_min,
                    "age_max": target_age_max,
                    "users": len(audience),
                    "recipients": len(recipients),
                },
            )
        return {
            "schedule_id": schedule_id,
            "smart_ad_id": smart_ad_id,
            "occasion": clean_occasion,
            "channel": channel,
            "scheduled_for": scheduled_utc,
            "target_gender": target_gender,
            "target_age_min": target_age_min,
            "target_age_max": target_age_max,
            "target_user_count": len(audience),
            "queued_recipient_count": len(recipients),
        }

    def delete_schedule(
        self, principal_id: UUID, tenant_id: UUID, schedule_id: UUID
    ) -> None:
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            exists = connection.execute(
                text(
                    """SELECT schedule_id FROM business_smart_ad_schedules
                    WHERE schedule_id=:schedule AND tenant_id=:tenant
                      AND account_id=:account FOR UPDATE"""
                ),
                {"schedule": schedule_id, "tenant": tenant_id, "account": account_id},
            ).scalar_one_or_none()
            if exists is None:
                raise SmartAdError(
                    "SMART_AD_UNAVAILABLE", "Scheduled advertisement is unavailable."
                )
            locked_jobs = int(
                connection.execute(
                    text(
                        """SELECT count(*) FROM communication_jobs
                        WHERE metadata->>'smart_ad_schedule_id'=:schedule
                          AND status IN ('PROCESSING','DELIVERED')"""
                    ),
                    {"schedule": str(schedule_id)},
                ).scalar_one()
            )
            if locked_jobs:
                raise SmartAdError(
                    "SMART_AD_SCHEDULE_LOCKED",
                    "A campaign that is sending or already delivered cannot be deleted.",
                )
            connection.execute(
                text(
                    """UPDATE communication_jobs
                    SET status='CANCELLED',last_error_code='SMART_AD_SCHEDULE_DELETED',
                        updated_at=now()
                    WHERE metadata->>'smart_ad_schedule_id'=:schedule
                      AND status IN ('QUEUED','RETRY')"""
                ),
                {"schedule": str(schedule_id)},
            )
            connection.execute(
                text(
                    """DELETE FROM business_smart_ad_schedules
                    WHERE schedule_id=:schedule AND tenant_id=:tenant AND account_id=:account"""
                ),
                {"schedule": schedule_id, "tenant": tenant_id, "account": account_id},
            )
