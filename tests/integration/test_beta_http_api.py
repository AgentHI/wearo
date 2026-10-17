from __future__ import annotations

import hashlib
import hmac
import io
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, create_engine, text

from apps.api.wearo_api.beta_profile import DailyQuotaService, PersonProfileService
from apps.api.wearo_api.browser_sessions import BrowserSessionService, SessionPolicy
from apps.api.wearo_api.consent import ConsentService
from apps.api.wearo_api.database import normalize_database_url
from apps.api.wearo_api.email_otp import AuthRealm, EmailOtpPolicy, EmailOtpService
from apps.api.wearo_api.http_api import ApiContainer, create_app
from apps.api.wearo_api.media_runtime import FilesystemPrivateBlobStore, PostgresMediaRuntime
from apps.api.wearo_api.postgres_auth import PostgresBrowserSessionStore, PostgresEmailOtpStore
from apps.api.wearo_api.postgres_beta import (
    PostgresConsentStore,
    PostgresProfileStore,
    PostgresQuotaStore,
)
from apps.api.wearo_api.render_runtime import PostgresRenderRuntime

pytestmark = pytest.mark.integration

PEPPER = b"http-api-integration-pepper-32-bytes"


class RecordingProvider:
    def __init__(self) -> None:
        self.code = ""

    def send_sign_in_code(
        self, *, to_email: str, code: str, expires_at: datetime, realm: AuthRealm
    ) -> None:
        self.code = code


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


def _image_bytes(color: tuple[int, int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (640, 800), color).save(output, format="PNG")
    return output.getvalue()


def _cleanup(engine: Engine, account_id: object, email_hash: bytes) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE consent_records DISABLE TRIGGER trg_consent_records_immutable")
        )
        try:
            for statement in (
                "DELETE FROM render_results WHERE account_id = :account",
                "DELETE FROM render_work_items WHERE account_id = :account",
                "DELETE FROM generation_daily_usage WHERE account_id = :account",
                "DELETE FROM render_jobs WHERE account_id = :account",
                "DELETE FROM render_quotes WHERE account_id = :account",
                "DELETE FROM person_profiles WHERE account_id = :account",
                "DELETE FROM consent_records WHERE account_id = :account",
                "DELETE FROM media_assets WHERE account_id = :account",
                "DELETE FROM sessions WHERE account_id = :account",
                "DELETE FROM principal_identities WHERE account_id = :account",
                "DELETE FROM principals WHERE account_id = :account",
                "DELETE FROM accounts WHERE account_id = :account",
            ):
                connection.execute(text(statement), {"account": account_id})
            connection.execute(
                text("DELETE FROM email_otp_requests WHERE normalized_email_hash = :email_hash"),
                {"email_hash": email_hash},
            )
        finally:
            connection.execute(
                text("ALTER TABLE consent_records ENABLE TRIGGER trg_consent_records_immutable")
            )


def test_authenticated_upload_consent_profile_and_allowance_flow(
    engine: Engine, tmp_path: Path
) -> None:
    account_id, principal_id, identity_id = uuid4(), uuid4(), uuid4()
    email = f"http-{identity_id.hex}@example.com"
    email_hash = hmac.new(PEPPER, b"email\0" + email.encode(), hashlib.sha256).digest()
    provider = RecordingProvider()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
            {"account": account_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO principals
                    (principal_id, account_id, account_kind, principal_type)
                VALUES
                    (:principal, :account, 'CONSUMER', 'CONSUMER')
                """
            ),
            {"principal": principal_id, "account": account_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO principal_identities
                    (identity_id, account_id, principal_id, channel, normalized_value)
                VALUES
                    (:identity, :account, :principal, 'EMAIL', :email)
                """
            ),
            {
                "identity": identity_id,
                "account": account_id,
                "principal": principal_id,
                "email": email,
            },
        )

    container = ApiContainer(
        engine=engine,
        otp=EmailOtpService(
            PostgresEmailOtpStore(engine), provider, EmailOtpPolicy(), pepper=PEPPER
        ),
        sessions=BrowserSessionService(
            PostgresBrowserSessionStore(engine), SessionPolicy(), pepper=PEPPER
        ),
        media=PostgresMediaRuntime(engine, FilesystemPrivateBlobStore(tmp_path / "private")),
        consents=ConsentService(PostgresConsentStore(engine), current_version="beta-v1"),
        profiles=PersonProfileService(PostgresProfileStore(engine)),
        quota=DailyQuotaService(PostgresQuotaStore(engine)),
        renders=PostgresRenderRuntime(engine),
        secure_cookie=True,
    )

    try:
        with TestClient(create_app(container), base_url="https://testserver") as client:
            assert client.get("/health").json() == {"status": "ok"}
            requested = client.post(
                "/api/v1/auth/email-otp/request",
                json={"destination": email, "purpose": "SIGN_IN"},
            )
            assert requested.status_code == 200
            verified = client.post(
                "/api/v1/auth/email-otp/verify",
                json={
                    "challenge_id": requested.json()["challenge_id"],
                    "code": provider.code,
                },
            )
            assert verified.status_code == 200
            assert verified.json()["has_person_profile"] is False
            csrf = verified.json()["csrf_token"]
            headers = {"X-CSRF-Token": csrf}

            gallery = client.get("/api/v1/renders")
            assert gallery.status_code == 200
            assert gallery.json() == {"items": [], "queue": [], "retention_days": 30}

            allowance = client.get("/api/v1/me/daily-allowance")
            assert allowance.status_code == 200
            assert allowance.json()["remaining"] == 3

            denied = client.post(
                "/api/v1/assets",
                data={"kind": "PERSON"},
                files={"image": ("person.png", _image_bytes((120, 100, 90)), "image/png")},
            )
            assert denied.status_code == 403

            person = client.post(
                "/api/v1/assets",
                headers=headers,
                data={"kind": "PERSON"},
                files={"image": ("person.png", _image_bytes((120, 100, 90)), "image/png")},
            )
            assert person.status_code == 201
            person_asset_id = person.json()["asset_id"]
            duplicate_person = client.post(
                "/api/v1/assets",
                headers=headers,
                data={"kind": "PERSON"},
                files={"image": ("person-again.png", _image_bytes((120, 100, 90)), "image/png")},
            )
            assert duplicate_person.status_code == 201
            assert duplicate_person.json()["asset_id"] == person_asset_id

            consent = client.post(
                "/api/v1/consents",
                headers=headers,
                json={
                    "subject_asset_id": person_asset_id,
                    "adult_confirmed": True,
                    "depicted_person_permission": True,
                    "transformation_approved": True,
                    "retention_notice_acknowledged": True,
                    "no_training_notice_acknowledged": True,
                },
            )
            assert consent.status_code == 201

            profile = client.put(
                "/api/v1/me/person-profile",
                headers=headers,
                json={
                    "person_asset_id": person_asset_id,
                    "consent_id": consent.json()["id"],
                    "height_cm": 170,
                },
            )
            assert profile.status_code == 200
            assert client.get("/api/v1/me/person-profile").json()["id"] == profile.json()["id"]

            item = client.post(
                "/api/v1/assets",
                headers=headers,
                data={"kind": "PRODUCT"},
                files={"image": ("shirt.png", _image_bytes((20, 60, 160)), "image/png")},
            )
            assert item.status_code == 201

            quote_id = uuid4()
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO render_quotes
                            (
                                quote_id,
                                account_id,
                                person_asset_id,
                                consent_id,
                                principal_id,
                                profile_id,
                                item_asset_id,
                                remaining_allowance,
                                provider,
                                model_version,
                                provider_region,
                                expires_at
                            )
                        VALUES
                            (
                                :quote,
                                :account,
                                :person,
                                :consent,
                                :principal,
                                :profile,
                                :item,
                                3,
                                'OPENAI',
                                'test-image-model',
                                'global',
                                now() + interval '10 minutes'
                            )
                        """
                    ),
                    {
                        "quote": quote_id,
                        "account": account_id,
                        "person": person_asset_id,
                        "consent": consent.json()["id"],
                        "principal": principal_id,
                        "profile": profile.json()["id"],
                        "item": item.json()["asset_id"],
                    },
                )
            delayed_job = container.renders.create_job(
                quote_id=quote_id,
                account_id=account_id,
                principal_id=principal_id,
                idempotency_key="http-cancel-delayed-job",
            )
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE render_jobs SET created_at = :created_at WHERE job_id = :job"),
                    {
                        "created_at": datetime.now(UTC) - timedelta(minutes=2),
                        "job": delayed_job.job_id,
                    },
                )

            queued = client.get("/api/v1/renders")
            assert queued.status_code == 200
            assert queued.json()["queue"][0]["can_cancel"] is True
            assert "cancel_after" in queued.json()["queue"][0]
            assert client.delete(f"/api/v1/renders/{delayed_job.job_id}").status_code == 403
            cancelled = client.delete(f"/api/v1/renders/{delayed_job.job_id}", headers=headers)
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "CANCELLED"

            stream_quote_id = uuid4()
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO render_quotes
                            (
                                quote_id,
                                account_id,
                                person_asset_id,
                                consent_id,
                                principal_id,
                                profile_id,
                                item_asset_id,
                                remaining_allowance,
                                provider,
                                model_version,
                                provider_region,
                                expires_at
                            )
                        SELECT
                            :stream_quote,
                            account_id,
                            person_asset_id,
                            consent_id,
                            principal_id,
                            profile_id,
                            item_asset_id,
                            remaining_allowance,
                            provider,
                            model_version,
                            provider_region,
                            now() + interval '10 minutes'
                        FROM render_quotes
                        WHERE quote_id = :source_quote
                        """
                    ),
                    {"stream_quote": stream_quote_id, "source_quote": quote_id},
                )
            stream_job = container.renders.create_job(
                quote_id=stream_quote_id,
                account_id=account_id,
                principal_id=principal_id,
                idempotency_key="http-progressive-preview",
            )
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE render_work_items
                        SET status = 'LEASED',
                            attempts = 1,
                            leased_by = 'http-test-worker',
                            lease_expires_at = now() + interval '3 minutes'
                        WHERE job_id = :job
                        """
                    ),
                    {"job": stream_job.job_id},
                )
                connection.execute(
                    text("UPDATE render_jobs SET status = 'PROCESSING' WHERE job_id = :job"),
                    {"job": stream_job.job_id},
                )
            container.media.store_progressive_preview(
                stream_job.job_id, _image_bytes((60, 80, 160))
            )
            partial = client.get(f"/api/v1/renders/{stream_job.job_id}/preview")
            assert partial.status_code == 200
            assert partial.headers["content-type"] == "image/png"
            unchanged = client.get(
                f"/api/v1/renders/{stream_job.job_id}/preview",
                headers={"If-None-Match": partial.headers["etag"]},
            )
            assert unchanged.status_code == 304
            container.media.clear_progressive_preview(stream_job.job_id)
            container.renders.complete_failure(stream_job.job_id, "HTTP_TEST_COMPLETE")

            unavailable = client.post(
                "/api/v1/quotes",
                headers=headers,
                json={"item_asset_id": item.json()["asset_id"]},
            )
            assert unavailable.status_code == 503
            assert unavailable.json()["code"] == "VISION_PROVIDER_UNAVAILABLE"

            deleted = client.delete("/api/v1/me/person-profile", headers=headers)
            assert deleted.status_code == 202
            missing_profile = client.get("/api/v1/me/person-profile")
            assert missing_profile.status_code == 404
            assert missing_profile.json()["code"] == "PROFILE_NOT_FOUND"
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
            assert client.get("/api/v1/me/daily-allowance").status_code == 401
    finally:
        _cleanup(engine, account_id, email_hash)
