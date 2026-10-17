from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, Header, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, create_engine, text

from .beta_profile import IST, DailyQuotaService, PersonProfile, PersonProfileService, ProfileError
from .browser_sessions import (
    BrowserSession,
    BrowserSessionService,
    SessionAuthenticationError,
    SessionPolicy,
)
from .consent import ConsentAttestation, ConsentError, ConsentService
from .database import normalize_database_url
from .durable_worker import DurableRenderWorker
from .email_otp import (
    AuthRealm,
    EmailDeliveryProvider,
    EmailOtpPolicy,
    EmailOtpService,
    OtpAuthenticationError,
)
from .environment import load_wearo_environment
from .external_runtime import (
    AnalysisServiceError,
    ApprovedBetaRouteRegistry,
    HttpAnalysisClient,
    OpenAIAnalysisClient,
)
from .image_preflight import ImagePreflightService, VisionAnalyzer
from .media_runtime import FilesystemPrivateBlobStore, MediaRuntimeError, PostgresMediaRuntime
from .postgres_auth import (
    DevelopmentPostgresOtpStore,
    PostgresBrowserSessionStore,
    PostgresEmailOtpStore,
)
from .postgres_beta import (
    PostgresConsentStore,
    PostgresProfileStore,
    PostgresQuotaStore,
    PostgresQuoteStore,
    decimal_or_none,
)
from .render_preflight import BetaRenderPreflightService, RenderPreflightError
from .render_runtime import DurableRenderError, DurableRenderJob, PostgresRenderRuntime
from .smtp_email import SmtpEmailDeliveryProvider, SmtpSettings

logger = logging.getLogger(__name__)


class ApiProblem(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class UnavailableEmailProvider:
    def send_sign_in_code(self, **_: object) -> None:
        raise ApiProblem(503, "EMAIL_DELIVERY_UNAVAILABLE", "Email delivery is not configured.")


@dataclass(frozen=True)
class ApiContainer:
    engine: Engine
    otp: EmailOtpService
    sessions: BrowserSessionService
    media: PostgresMediaRuntime
    consents: ConsentService
    profiles: PersonProfileService
    quota: DailyQuotaService
    renders: PostgresRenderRuntime
    preflight: BetaRenderPreflightService | None = None
    secure_cookie: bool = True


class OtpRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str
    purpose: str = "SIGN_IN"


class OtpVerifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    code: str = Field(min_length=4, max_length=8)


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_asset_id: UUID
    adult_confirmed: bool
    depicted_person_permission: bool
    transformation_approved: bool
    retention_notice_acknowledged: bool
    no_training_notice_acknowledged: bool


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_asset_id: UUID
    consent_id: UUID
    height_cm: float | None = Field(default=None, ge=80, le=260)
    weight_kg: float | None = Field(default=None, ge=20, le=350)


class QuoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_asset_id: UUID


class RenderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: UUID


def _problem(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": request_id},
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid4().hex)


def _authenticate(
    request: Request,
    container: ApiContainer,
    *,
    mutation: bool = False,
    csrf_token: str | None = None,
) -> BrowserSession:
    token = request.cookies.get("wearo_session", "")
    try:
        return container.sessions.authenticate(
            token,
            expected_realm="SHOP",
            csrf_token=csrf_token,
            mutation=mutation,
        )
    except SessionAuthenticationError:
        status = 403 if token and mutation else 401
        raise ApiProblem(status, "AUTHENTICATION_REQUIRED", "Authentication required.") from None


def _profile_json(profile: PersonProfile) -> dict[str, Any]:
    return {
        "id": profile.profile_id,
        "person_asset_id": profile.person_asset_id,
        "consent_id": profile.consent_id,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "status": profile.status,
        "last_used_at": profile.last_used_at,
    }


def _job_json(job: DurableRenderJob) -> dict[str, Any]:
    states = {"PENDING": "QUEUED", "DELIVERED": "SUCCEEDED"}
    charge_states = {
        "PENDING": "RESERVED",
        "PROCESSING": "RESERVED",
        "DELIVERED": "SETTLED",
        "FAILED": "RELEASED",
        "CANCELLED": "RELEASED",
    }
    return {
        "render_id": job.job_id,
        "quote_id": job.quote_id,
        "status": states.get(job.status, job.status),
        "charge_status": charge_states[job.status],
        "cost_wearo_tokens": 0,
        "error_code": job.error_code,
        "result_asset_id": job.result_asset_id,
        "status_url": f"/api/v1/renders/{job.job_id}",
    }


def create_app(
    container: ApiContainer,
    *,
    embedded_worker: DurableRenderWorker | None = None,
) -> FastAPI:
    stop_worker = threading.Event()
    worker_thread: threading.Thread | None = None

    def run_embedded_worker() -> None:
        worker = embedded_worker
        if worker is None:
            return
        while not stop_worker.is_set():
            try:
                worker.recover_stale()
                outcome = worker.run_once()
            except Exception:
                logger.exception("Local embedded render worker iteration failed")
                stop_worker.wait(2)
                continue
            if not outcome.claimed:
                stop_worker.wait(1)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal worker_thread
        if embedded_worker is not None:
            worker_thread = threading.Thread(
                target=run_embedded_worker,
                name="wearo-local-render-worker",
                daemon=True,
            )
            worker_thread.start()
        try:
            yield
        finally:
            stop_worker.set()
            if worker_thread is not None:
                worker_thread.join(timeout=1)

    app = FastAPI(title="Wearo beta API", version="1.0.0-beta", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request.state.request_id = request.headers.get("X-Request-Id", uuid4().hex)[:100]
        response: Response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiProblem)
    async def api_problem(request: Request, error: ApiProblem) -> JSONResponse:
        return _problem(error.status, error.code, str(error), _request_id(request))

    @app.exception_handler(ProfileError)
    @app.exception_handler(ConsentError)
    @app.exception_handler(MediaRuntimeError)
    @app.exception_handler(RenderPreflightError)
    @app.exception_handler(DurableRenderError)
    async def domain_problem(request: Request, error: ValueError) -> JSONResponse:
        code = getattr(error, "code", "VALIDATION_FAILED")
        if code == "JOB_UNAVAILABLE":
            status = 404
        elif code in {
            "JOB_STATE_CONFLICT",
            "QUOTA_STATE_CONFLICT",
            "QUEUE_CANCELLATION_TOO_EARLY",
        }:
            status = 409
        else:
            status = 422
        return _problem(status, code, str(error), _request_id(request))

    @app.exception_handler(AnalysisServiceError)
    async def analysis_problem(request: Request, error: AnalysisServiceError) -> JSONResponse:
        return _problem(
            503,
            "VISION_PROVIDER_UNAVAILABLE",
            "Image understanding is temporarily unavailable.",
            _request_id(request),
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        with container.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness() -> dict[str, str]:
        with container.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        if container.preflight is None:
            raise ApiProblem(
                503,
                "VISION_PROVIDER_UNAVAILABLE",
                "Image understanding is not configured for this environment.",
            )
        return {"status": "ready", "image_understanding": "configured"}

    @app.post("/api/v1/auth/email-otp/request")
    def request_otp(body: OtpRequestBody) -> dict[str, Any]:
        realm: AuthRealm = "BUSINESS" if body.purpose == "BUSINESS_SIGN_IN" else "SHOP"
        result = container.otp.request_code(body.destination, realm)
        return {
            "challenge_id": result.challenge_id,
            "expires_at": result.expires_at,
            "message": result.message,
        }

    @app.post("/api/v1/auth/email-otp/verify")
    def verify_otp(body: OtpVerifyBody, response: Response) -> dict[str, Any]:
        try:
            result = container.otp.verify_code(body.challenge_id, body.code)
        except OtpAuthenticationError:
            raise ApiProblem(401, "INVALID_OTP", "Invalid or expired sign-in code.") from None
        try:
            container.profiles.require(result.account_id)
            has_person_profile = True
        except ProfileError:
            has_person_profile = False
        response.set_cookie(
            "wearo_session",
            result.session_token,
            max_age=EmailOtpPolicy().session_ttl.days * 86400,
            httponly=True,
            secure=container.secure_cookie,
            samesite="lax",
            path="/",
        )
        return {
            "id": result.principal_id,
            "account_id": result.account_id,
            "type": "CONSUMER" if result.realm == "SHOP" else "BUSINESS",
            "verified": True,
            "has_person_profile": has_person_profile,
            "csrf_token": result.csrf_token,
            "expires_at": result.expires_at,
        }

    @app.post("/api/v1/auth/logout")
    def logout(
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        container.sessions.logout(request.cookies["wearo_session"], x_csrf_token or "")
        response.delete_cookie(
            "wearo_session", path="/", secure=container.secure_cookie, httponly=True
        )
        return {"ok": True}

    @app.post("/api/v1/assets", status_code=201)
    async def upload_asset(
        request: Request,
        kind: Annotated[str, Form()],
        image: Annotated[UploadFile, File()],
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        content = await image.read(container.media.maximum_bytes + 1)
        stored = container.media.store(
            session.account_id,
            kind=kind,
            content=content,
            content_type=image.content_type or "",
        )
        return asdict(stored)

    @app.get("/api/v1/assets/{asset_id}")
    def read_asset(asset_id: UUID, request: Request) -> Response:
        session = _authenticate(request, container)
        content, content_type = container.media.read_owned(asset_id, session.account_id)
        return Response(content=content, media_type=content_type)

    @app.post("/api/v1/consents", status_code=201)
    def create_consent(
        body: ConsentBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        evidence = container.consents.accept(
            account_id=session.account_id,
            actor_principal_id=session.principal_id,
            asset_id=body.subject_asset_id,
            purpose="TRY_ON",
            attestation=ConsentAttestation(
                adult_confirmed=body.adult_confirmed,
                depicted_person_permission=body.depicted_person_permission,
                transformation_approved=body.transformation_approved,
                retention_notice_acknowledged=body.retention_notice_acknowledged,
                no_training_notice_acknowledged=body.no_training_notice_acknowledged,
            ),
        )
        return {
            "id": evidence.consent_id,
            "accepted_at": evidence.accepted_at,
            "consent_version": evidence.consent_version,
            "purpose": evidence.purpose,
        }

    @app.get("/api/v1/me/person-profile")
    def get_profile(request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        try:
            profile = container.profiles.require(session.account_id)
        except ProfileError:
            raise ApiProblem(404, "PROFILE_NOT_FOUND", "No active person profile exists.") from None
        return _profile_json(profile)

    @app.put("/api/v1/me/person-profile")
    def put_profile(
        body: ProfileBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        evidence = container.consents.require_current(
            account_id=session.account_id,
            actor_principal_id=session.principal_id,
            asset_id=body.person_asset_id,
            purpose="TRY_ON",
        )
        if evidence.consent_id != body.consent_id:
            raise ConsentError("affirmative consent is required")
        profile = PersonProfile(
            profile_id=uuid4(),
            account_id=session.account_id,
            principal_id=session.principal_id,
            person_asset_id=body.person_asset_id,
            consent_id=body.consent_id,
            height_cm=decimal_or_none(body.height_cm),
            weight_kg=decimal_or_none(body.weight_kg),
            status="ACTIVE",
            last_used_at=None,
        )
        container.profiles.save(profile)
        return _profile_json(profile)

    @app.delete("/api/v1/me/person-profile", status_code=202)
    def delete_profile(
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        try:
            profile = container.profiles.require(session.account_id)
        except ProfileError:
            raise ApiProblem(404, "PROFILE_NOT_FOUND", "No active person profile exists.") from None
        container.profiles.delete(profile.profile_id, session.account_id)
        return {"ok": True}

    @app.get("/api/v1/me/daily-allowance")
    def daily_allowance(request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        current = datetime.now(UTC)
        usage_date = container.quota.usage_date(current)
        usage = container.quota.store.get(session.account_id, usage_date)
        used = usage.successful_generations if usage else 0
        ist = current.astimezone(IST)
        reset_local = datetime.combine(ist.date() + timedelta(days=1), time(), ist.tzinfo)
        return {
            "successful_limit": container.quota.maximum,
            "successful_used": used,
            "remaining": (
                container.quota.maximum
                if not container.quota.limit_enabled
                else container.quota.maximum - used
            ),
            "unlimited": not container.quota.limit_enabled,
            "resets_at": reset_local.astimezone(UTC),
            "active_job_id": (
                usage.active_job_id if usage and container.quota.limit_enabled else None
            ),
        }

    @app.post("/api/v1/quotes", status_code=201)
    def create_quote(
        body: QuoteBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.preflight is None:
            raise ApiProblem(
                503,
                "VISION_PROVIDER_UNAVAILABLE",
                "Image understanding is not configured for this environment.",
            )
        profile = container.profiles.require(session.account_id)
        person_image, _ = container.media.read_prepared(
            profile.person_asset_id, session.account_id, "PERSON"
        )
        item_image, _ = container.media.read_prepared(
            body.item_asset_id, session.account_id, "GARMENT"
        )
        quote = container.preflight.quote(
            account_id=session.account_id,
            principal_id=session.principal_id,
            item_asset_id=body.item_asset_id,
            person_image=person_image,
            item_image=item_image,
        )
        return {
            "quote_id": quote.quote_id,
            "remaining_allowance": quote.remaining_before,
            "expires_at": quote.expires_at,
            "disclaimer": quote.limitation,
        }

    @app.post("/api/v1/renders", status_code=202)
    def create_render(
        body: RenderBody,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        job = container.renders.create_job(
            quote_id=body.quote_id,
            account_id=session.account_id,
            principal_id=session.principal_id,
            idempotency_key=idempotency_key,
        )
        return _job_json(job)

    @app.get("/api/v1/renders")
    def list_renders(request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        items = container.renders.list_gallery(session.account_id)
        queue = container.renders.list_queue_activity(session.account_id)
        return {
            "items": [
                {
                    "result_id": item.result_id,
                    "render_id": item.render_id,
                    "result_asset_id": item.result_asset_id,
                    "created_at": item.created_at,
                    "expires_at": item.expires_at,
                }
                for item in items
            ],
            "queue": [
                {
                    "render_id": item.render_id,
                    "status": {"PENDING": "QUEUED"}.get(item.status, item.status),
                    "attempts": item.attempts,
                    "error_code": item.error_code,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "cancel_after": item.cancel_after,
                    "can_cancel": item.can_cancel,
                }
                for item in queue
            ],
            "retention_days": 30,
        }

    @app.delete("/api/v1/renders/{render_id}")
    def cancel_render(
        render_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        job = container.renders.cancel_queued(render_id, session.account_id)
        container.media.clear_progressive_preview(render_id)
        return _job_json(job)

    @app.get("/api/v1/renders/{render_id}/preview")
    def get_progressive_preview(
        render_id: UUID,
        request: Request,
        if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    ) -> Response:
        session = _authenticate(request, container)
        job = container.renders.get_job(render_id, session.account_id)
        if job is None:
            raise ApiProblem(404, "RENDER_UNAVAILABLE", "Render is unavailable.")
        if job.status != "PROCESSING":
            return Response(status_code=204)
        partial = container.media.read_progressive_preview(render_id)
        if partial is None:
            return Response(status_code=204)
        content, content_type = partial
        etag = f'"{hashlib.sha256(content).hexdigest()}"'
        if if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return Response(content=content, media_type=content_type, headers={"ETag": etag})

    @app.get("/api/v1/renders/{render_id}")
    def get_render(render_id: UUID, request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        job = container.renders.get_job(render_id, session.account_id)
        if job is None:
            raise ApiProblem(404, "RENDER_UNAVAILABLE", "Render is unavailable.")
        return _job_json(job)

    return app


def _smtp_provider_from_env() -> EmailDeliveryProvider:
    host = os.environ.get("WEARO_SMTP_HOST", "")
    if not host:
        return UnavailableEmailProvider()
    return SmtpEmailDeliveryProvider(
        SmtpSettings(
            host=host,
            port=int(os.environ.get("WEARO_SMTP_PORT", "587")),
            username=os.environ.get("WEARO_SMTP_USERNAME", ""),
            password=os.environ.get("WEARO_SMTP_PASSWORD", ""),
            from_address=os.environ.get("WEARO_SMTP_FROM", ""),
            use_tls=os.environ.get("WEARO_SMTP_TLS", "true").casefold() == "true",
        )
    )


def create_app_from_env() -> FastAPI:
    load_wearo_environment()
    database_url = os.environ.get("WEARO_DATABASE_URL", "")
    pepper = os.environ.get("WEARO_AUTH_PEPPER", "").encode()
    if not database_url:
        raise RuntimeError("WEARO_DATABASE_URL is required")
    if len(pepper) < 32:
        raise RuntimeError("WEARO_AUTH_PEPPER must contain at least 32 bytes")
    secure_cookie = os.environ.get("WEARO_SECURE_COOKIE", "true").casefold() == "true"
    test_auth_enabled = os.environ.get("WEARO_TEST_AUTH_ENABLED", "false").casefold() == "true"
    embedded_worker_enabled = (
        os.environ.get("WEARO_LOCAL_EMBEDDED_WORKER", "false").casefold() == "true"
    )
    daily_limit_enabled = os.environ.get("WEARO_DAILY_LIMIT_ENABLED", "true").casefold() == "true"
    if test_auth_enabled and secure_cookie:
        raise RuntimeError("test authentication requires WEARO_SECURE_COOKIE=false")
    if embedded_worker_enabled and not test_auth_enabled:
        raise RuntimeError("embedded worker is restricted to local test authentication")
    fixed_test_code = os.environ.get("WEARO_TEST_OTP_CODE", "1324") if test_auth_enabled else None
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    storage_root = Path(os.environ.get("WEARO_PRIVATE_STORAGE_ROOT", ".wearo-storage"))
    consent_service = ConsentService(PostgresConsentStore(engine), current_version="beta-v1")
    profile_service = PersonProfileService(PostgresProfileStore(engine))
    quota_service = DailyQuotaService(PostgresQuotaStore(engine), limit_enabled=daily_limit_enabled)
    analysis_endpoint = os.environ.get("WEARO_ANALYSIS_ENDPOINT", "")
    analysis_token = os.environ.get("WEARO_ANALYSIS_TOKEN", "")
    selected_provider = os.environ.get("WEARO_RENDER_PROVIDER", "GOOGLE_VERTEX").strip().upper()
    if selected_provider == "OPENAI":
        openai_api_key = os.environ.get("WEARO_OPENAI_API_KEY", "")
        route_model = os.environ.get("WEARO_OPENAI_MODEL", "gpt-image-2.5-sunburst")
        route_region = "global"
        route_enabled = os.environ.get(
            "WEARO_OPENAI_ENABLED", "false"
        ).casefold() == "true" and bool(openai_api_key)
    elif selected_provider == "GOOGLE_VERTEX":
        route_model = "virtual-try-on-001"
        route_region = os.environ.get("WEARO_VERTEX_REGION", "asia-southeast1")
        route_enabled = os.environ.get(
            "WEARO_VERTEX_ENABLED", "false"
        ).casefold() == "true" and bool(os.environ.get("WEARO_VERTEX_PROJECT_ID", ""))
    else:
        raise RuntimeError("WEARO_RENDER_PROVIDER must be OPENAI or GOOGLE_VERTEX")
    analyzer: VisionAnalyzer | None = None
    if route_enabled and analysis_endpoint and analysis_token:
        analyzer = HttpAnalysisClient(analysis_endpoint, bearer_token=analysis_token)
    elif route_enabled and selected_provider == "OPENAI":
        analyzer = OpenAIAnalysisClient(
            api_key=openai_api_key,
            model=os.environ.get("WEARO_OPENAI_ANALYSIS_MODEL", "gpt-6-luna"),
        )
    preflight = None
    if analyzer is not None:
        preflight = BetaRenderPreflightService(
            profile_service,
            consent_service,
            ImagePreflightService(analyzer),
            quota_service,
            ApprovedBetaRouteRegistry(
                enabled=True,
                provider=selected_provider,
                model=route_model,
                region=route_region,
            ),
            PostgresQuoteStore(engine),
        )
    container = ApiContainer(
        engine=engine,
        otp=EmailOtpService(
            DevelopmentPostgresOtpStore(engine)
            if test_auth_enabled
            else PostgresEmailOtpStore(engine),
            _smtp_provider_from_env(),
            EmailOtpPolicy(),
            pepper=pepper,
            fixed_test_code=fixed_test_code,
        ),
        sessions=BrowserSessionService(
            PostgresBrowserSessionStore(engine), SessionPolicy(), pepper=pepper
        ),
        media=PostgresMediaRuntime(engine, FilesystemPrivateBlobStore(storage_root)),
        consents=consent_service,
        profiles=profile_service,
        quota=quota_service,
        renders=PostgresRenderRuntime(engine, enforce_daily_allowance=daily_limit_enabled),
        preflight=preflight,
        secure_cookie=secure_cookie,
    )
    embedded_worker = None
    if embedded_worker_enabled:
        from .worker_process import build_worker

        embedded_worker = build_worker()
    return create_app(container, embedded_worker=embedded_worker)
