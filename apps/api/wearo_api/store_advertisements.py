# ruff: noqa: E501
from __future__ import annotations

import base64
import io
from datetime import date
from uuid import UUID

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Engine, text

from .media_runtime import PostgresMediaRuntime

CARD_WIDTH = 768
CARD_HEIGHT = 1024
MAX_AI_ATTEMPTS = 3


class StoreAdvertisementError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def crop_card(content: bytes) -> bytes:
    """Center-crop and bound cards below the consumer try-on canvas footprint."""
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(image, (CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, "JPEG", quality=88, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise StoreAdvertisementError(
            "INVALID_ADVERTISEMENT_IMAGE", "Upload a valid JPEG, PNG, or WebP image."
        ) from None


class OpenAIAdvertisementGenerator:
    endpoint = "https://api.openai.com/v1/images/generations"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str) -> bytes:
        if not self.api_key:
            raise StoreAdvertisementError(
                "ADVERTISEMENT_AI_UNAVAILABLE", "AI advertisement generation is not configured."
            )
        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "prompt": "Create a polished premium retail advertisement card. No small print. "
                + prompt,
                "size": "1024x1536",
                "quality": "high",
                "output_format": "png",
                "n": 1,
            },
            timeout=180,
        )
        if response.status_code != 200:
            raise StoreAdvertisementError(
                "ADVERTISEMENT_AI_FAILED", "The advertisement could not be generated. Try again."
            )
        try:
            encoded = response.json()["data"][0]["b64_json"]
            return base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, TypeError, ValueError, requests.JSONDecodeError):
            raise StoreAdvertisementError(
                "ADVERTISEMENT_AI_FAILED", "The advertisement could not be generated. Try again."
            ) from None


class PostgresStoreAdvertisements:
    def __init__(
        self, engine: Engine, media: PostgresMediaRuntime, generator: OpenAIAdvertisementGenerator
    ) -> None:
        self.engine = engine
        self.media = media
        self.generator = generator

    def _context(self, principal_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""SELECT s.store_id, s.tenant_id, s.account_id,
                t.advertisements_enabled FROM business_stores s JOIN business_tenants t
                ON t.tenant_id=s.tenant_id AND t.account_id=s.account_id
                WHERE s.admin_principal_id=:principal AND s.status='ACTIVE'"""),
                    {"principal": principal_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None or not row["advertisements_enabled"]:
            raise StoreAdvertisementError(
                "ADVERTISEMENT_FEATURE_UNAVAILABLE",
                "Advertisements require a Premium Business plan.",
            )
        return dict(row)

    def list(self, principal_id: UUID) -> dict[str, object]:
        context = self._context(principal_id)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("""SELECT a.advertisement_id, a.title, a.prompt, a.asset_id,
                a.source, a.ai_attempts, a.created_at, a.updated_at,
                (x.advertisement_id IS NOT NULL) active_today
                FROM store_advertisements a LEFT JOIN store_advertisement_activations x
                  ON x.store_id=a.store_id AND x.advertisement_id=a.advertisement_id
                 AND x.active_date=(now() AT TIME ZONE 'Asia/Kolkata')::date
                WHERE a.store_id=:store_id AND a.account_id=:account_id
                ORDER BY a.updated_at DESC"""),
                context,
            ).mappings()
            return {"items": [dict(row) for row in rows], "maximum_ai_attempts": MAX_AI_ATTEMPTS}

    def upload(self, principal_id: UUID, title: str, content: bytes) -> dict[str, object]:
        context = self._context(principal_id)
        clean_title = title.strip()
        if not clean_title or len(clean_title) > 120:
            raise StoreAdvertisementError(
                "INVALID_ADVERTISEMENT_TITLE", "Enter a title under 120 characters."
            )
        cropped = crop_card(content)
        asset = self.media.store_advertisement(
            UUID(str(context["account_id"])), cropped, "image/jpeg"
        )
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text("""INSERT INTO store_advertisements
                (store_id, tenant_id, account_id, title, asset_id, source)
                VALUES (:store_id, :tenant_id, :account_id, :title, :asset, 'UPLOAD')
                RETURNING advertisement_id, title, prompt, asset_id, source, ai_attempts, created_at, updated_at"""),
                    {**context, "title": clean_title, "asset": asset.asset_id},
                )
                .mappings()
                .one()
            )
        return dict(row)

    def generate(
        self, principal_id: UUID, title: str, prompt: str, advertisement_id: UUID | None = None
    ) -> dict[str, object]:
        context = self._context(principal_id)
        clean_title, clean_prompt = title.strip(), prompt.strip()
        if (
            not clean_title
            or len(clean_title) > 120
            or not clean_prompt
            or len(clean_prompt) > 1000
        ):
            raise StoreAdvertisementError(
                "INVALID_ADVERTISEMENT_DETAILS",
                "Enter a title and a prompt under 1,000 characters.",
            )
        attempts: int | None = 0
        if advertisement_id is not None:
            with self.engine.connect() as connection:
                attempts = connection.execute(
                    text("""SELECT ai_attempts FROM store_advertisements
                    WHERE advertisement_id=:advertisement AND store_id=:store_id AND account_id=:account_id"""),
                    {**context, "advertisement": advertisement_id},
                ).scalar_one_or_none()
            if attempts is None:
                raise StoreAdvertisementError(
                    "ADVERTISEMENT_UNAVAILABLE", "Advertisement unavailable."
                )
        if attempts is not None and attempts >= MAX_AI_ATTEMPTS:
            raise StoreAdvertisementError(
                "ADVERTISEMENT_AI_LIMIT_REACHED",
                "All 3 AI generation tries have been used for this card.",
            )
        # Reserve regeneration attempts before the external call so concurrent requests cannot exceed the cap.
        if advertisement_id is not None:
            with self.engine.begin() as connection:
                reserved = connection.execute(
                    text("""UPDATE store_advertisements SET ai_attempts=ai_attempts+1,
                    title=:title, prompt=:prompt, updated_at=now()
                    WHERE advertisement_id=:advertisement AND store_id=:store_id AND ai_attempts < 3
                    RETURNING advertisement_id"""),
                    {
                        **context,
                        "advertisement": advertisement_id,
                        "title": clean_title,
                        "prompt": clean_prompt,
                    },
                ).scalar_one_or_none()
            if reserved is None:
                raise StoreAdvertisementError(
                    "ADVERTISEMENT_AI_LIMIT_REACHED",
                    "All 3 AI generation tries have been used for this card.",
                )
        generated = crop_card(self.generator.generate(clean_prompt))
        asset = self.media.store_advertisement(
            UUID(str(context["account_id"])), generated, "image/jpeg"
        )
        with self.engine.begin() as connection:
            if advertisement_id is None:
                row = (
                    connection.execute(
                        text("""INSERT INTO store_advertisements
                    (store_id, tenant_id, account_id, title, prompt, asset_id, source, ai_attempts)
                    VALUES (:store_id, :tenant_id, :account_id, :title, :prompt, :asset, 'AI', 1)
                    RETURNING advertisement_id, title, prompt, asset_id, source, ai_attempts, created_at, updated_at"""),
                        {
                            **context,
                            "title": clean_title,
                            "prompt": clean_prompt,
                            "asset": asset.asset_id,
                        },
                    )
                    .mappings()
                    .one()
                )
            else:
                row = (
                    connection.execute(
                        text("""UPDATE store_advertisements SET asset_id=:asset, source='AI', updated_at=now()
                    WHERE advertisement_id=:advertisement AND store_id=:store_id
                    RETURNING advertisement_id, title, prompt, asset_id, source, ai_attempts, created_at, updated_at"""),
                        {**context, "asset": asset.asset_id, "advertisement": advertisement_id},
                    )
                    .mappings()
                    .one()
                )
        return dict(row)

    def update(self, principal_id: UUID, advertisement_id: UUID, title: str) -> dict[str, object]:
        context = self._context(principal_id)
        clean_title = title.strip()
        if not clean_title or len(clean_title) > 120:
            raise StoreAdvertisementError(
                "INVALID_ADVERTISEMENT_TITLE", "Enter a title under 120 characters."
            )
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text("""UPDATE store_advertisements SET title=:title, updated_at=now()
                WHERE advertisement_id=:advertisement AND store_id=:store_id AND account_id=:account_id
                RETURNING advertisement_id, title, prompt, asset_id, source, ai_attempts, created_at, updated_at"""),
                    {**context, "advertisement": advertisement_id, "title": clean_title},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise StoreAdvertisementError("ADVERTISEMENT_UNAVAILABLE", "Advertisement unavailable.")
        return dict(row)

    def activate(
        self, principal_id: UUID, advertisement_id: UUID, active_date: date
    ) -> dict[str, object]:
        context = self._context(principal_id)
        with self.engine.begin() as connection:
            exists = connection.execute(
                text("""SELECT 1 FROM store_advertisements
                WHERE advertisement_id=:advertisement AND store_id=:store_id AND account_id=:account_id"""),
                {**context, "advertisement": advertisement_id},
            ).scalar_one_or_none()
            if exists is None:
                raise StoreAdvertisementError(
                    "ADVERTISEMENT_UNAVAILABLE", "Advertisement unavailable."
                )
            connection.execute(
                text("""INSERT INTO store_advertisement_activations
                (store_id, active_date, advertisement_id) VALUES (:store_id, :active_date, :advertisement)
                ON CONFLICT (store_id, active_date) DO UPDATE SET advertisement_id=EXCLUDED.advertisement_id, activated_at=now()"""),
                {**context, "active_date": active_date, "advertisement": advertisement_id},
            )
        return {"advertisement_id": advertisement_id, "active_date": active_date}

    def image(self, principal_id: UUID, advertisement_id: UUID) -> tuple[bytes, str]:
        context = self._context(principal_id)
        with self.engine.connect() as connection:
            asset_id = connection.execute(
                text("""SELECT asset_id FROM store_advertisements
                WHERE advertisement_id=:advertisement AND store_id=:store_id AND account_id=:account_id"""),
                {**context, "advertisement": advertisement_id},
            ).scalar_one_or_none()
        if asset_id is None:
            raise StoreAdvertisementError("ADVERTISEMENT_UNAVAILABLE", "Advertisement unavailable.")
        return self.media.read_owned(asset_id, UUID(str(context["account_id"])))

    def active_for_sponsored_session(
        self,
        session_id: UUID,
        consumer_account_id: UUID,
        consumer_principal_id: UUID,
    ) -> tuple[bytes, str] | None:
        """Return today's store card only to the consumer who owns the sponsored session."""
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""SELECT advertisement.asset_id, session.business_account_id
                FROM business_sponsored_sessions session
                JOIN business_stores selected_store
                  ON selected_store.account_id=session.business_account_id
                 AND selected_store.tenant_id=session.tenant_id
                 AND selected_store.status='ACTIVE'
                 AND (selected_store.store_id=session.store_id OR
                      (session.store_id IS NULL AND selected_store.code='main'))
                JOIN store_advertisement_activations activation
                  ON activation.store_id=selected_store.store_id
                 AND activation.active_date=(now() AT TIME ZONE 'Asia/Kolkata')::date
                JOIN store_advertisements advertisement
                  ON advertisement.advertisement_id=activation.advertisement_id
                 AND advertisement.store_id=selected_store.store_id
                 AND advertisement.account_id=session.business_account_id
                JOIN business_tenants tenant
                  ON tenant.tenant_id=session.tenant_id
                 AND tenant.account_id=session.business_account_id
                 AND tenant.advertisements_enabled=true
                WHERE session.session_id=:session
                  AND session.consumer_account_id=:consumer_account
                  AND session.consumer_principal_id=:consumer_principal
                  AND session.status='ACTIVE' AND session.expires_at > now()"""),
                    {
                        "session": session_id,
                        "consumer_account": consumer_account_id,
                        "consumer_principal": consumer_principal_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return self.media.read_owned(row["asset_id"], row["business_account_id"])
