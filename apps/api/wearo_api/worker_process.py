from __future__ import annotations

import argparse
import logging
import os
import socket
import threading
from decimal import Decimal
from typing import Any, Protocol, TypedDict, cast

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from .database import create_database_engine
from .durable_worker import DurableRenderWorker, WorkerProvider
from .environment import load_wearo_environment
from .external_runtime import (
    GoogleDefaultAccessTokenProvider,
    HttpAnalysisClient,
    OpenAIAnalysisClient,
    RequestsJsonTransport,
    RequestsMultipartTransport,
)
from .google_drive import DriveSyncWorker, GoogleDriveConfig, GoogleDriveService
from .media_runtime import PostgresMediaRuntime, private_blob_store_from_env
from .render_provider import (
    BytePlusImageGenerationAdapter,
    OpenAIImageEditAdapter,
    ProviderError,
    RenderRequest,
    RenderResponse,
    VertexTryOnAdapter,
    person_preserving_negative_prompt,
    person_preserving_prompt,
    runware_aspect_dimensions,
)
from .render_quality import QualityAnalyzer, RenderQualityGate
from .render_quality_strategy import quality_parameters
from .render_runtime import DurableRenderJob, PostgresRenderRuntime
from .worker_health import start_worker_health_server

LOGGER = logging.getLogger(__name__)


class _GenerationAdapter(Protocol):
    def generate(
        self, *, model: str, prompt: str, images: list[bytes], parameters: dict[str, Any]
    ) -> Any: ...


class _CostLabProductionAdapter:
    """Adapt a promoted Cost Lab model to the production worker contract."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        region: str,
        base_url: str,
        api_key: str,
        request_parameters: dict[str, Any] | None = None,
    ) -> None:
        from apps.cost_lab_api.adapters import (
            BFLAdapter,
            BytePlusAdapter,
            OpenAICompatibleAdapter,
            RunwareAdapter,
        )

        adapters = {
            "OPENAI_COMPATIBLE": OpenAICompatibleAdapter,
            "BYTEPLUS": BytePlusAdapter,
            "BFL": BFLAdapter,
            "RUNWARE": RunwareAdapter,
        }
        adapter_type = adapters.get(provider)
        if adapter_type is None:
            raise ProviderError("PROVIDER_ADAPTER_UNSUPPORTED", retryable=False)
        self.provider = provider
        self.model = model
        self.region = region
        self.request_parameters = request_parameters or {}
        self.adapter = cast(_GenerationAdapter, adapter_type(base_url, api_key, 180))

    def render(self, request: RenderRequest) -> RenderResponse:
        from apps.cost_lab_api.app import (
            _RUNWARE_EARRINGS_ONLY_NEGATIVE_PROMPT,
            _RUNWARE_EARRINGS_ONLY_PROMPT,
            _RUNWARE_JEWELLERY_NEGATIVE_PROMPT,
            _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT,
            _RUNWARE_NECKLACE_ONLY_PROMPT,
            _RUNWARE_SPLIT_JEWELLERY_NEGATIVE_PROMPT,
            _RUNWARE_SPLIT_JEWELLERY_PROMPT,
            _benchmark_prompt,
        )
        from apps.cost_lab_api.jewellery_references import (
            plan_runware_jewellery_references,
        )

        reference_images = [request.person_image, request.item_image]
        prompt = (
            _benchmark_prompt("JEWELLERY")
            if request.product_kind == "JEWELLERY"
            else OpenAIImageEditAdapter.prompt
        )
        parameters = dict(self.request_parameters)
        strategy_provider = "OPENAI" if self.provider == "OPENAI_COMPATIBLE" else self.provider
        parameters |= quality_parameters(strategy_provider, self.model, request.quality)
        if self.provider == "RUNWARE":
            target_dimension = int(parameters["width"])
            parameters |= runware_aspect_dimensions(
                request.person_image,
                target_dimension=target_dimension,
            )
        if (
            self.provider == "RUNWARE"
            and self.model == "runware:400@4"
            and (request.product_kind == "JEWELLERY")
        ):
            plan = plan_runware_jewellery_references(request.person_image, request.item_image)
            reference_images = list(plan.images)
            prompts = {
                "person_necklace": _RUNWARE_NECKLACE_ONLY_PROMPT,
                "person_earring": _RUNWARE_EARRINGS_ONLY_PROMPT,
                "person_necklace_earring": _RUNWARE_SPLIT_JEWELLERY_PROMPT,
                "person_combined_product": _benchmark_prompt("JEWELLERY"),
            }
            negatives = {
                "person_necklace": _RUNWARE_NECKLACE_ONLY_NEGATIVE_PROMPT,
                "person_earring": _RUNWARE_EARRINGS_ONLY_NEGATIVE_PROMPT,
                "person_necklace_earring": _RUNWARE_SPLIT_JEWELLERY_NEGATIVE_PROMPT,
                "person_combined_product": _RUNWARE_JEWELLERY_NEGATIVE_PROMPT,
            }
            prompt = prompts[plan.strategy]
            configured_negative = str(parameters.get("negativePrompt") or "").strip()
            parameters["negativePrompt"] = (
                f"{negatives[plan.strategy]}, {configured_negative}"
                if configured_negative
                else negatives[plan.strategy]
            )
        prompt = person_preserving_prompt(prompt)
        if self.provider == "RUNWARE":
            parameters["negativePrompt"] = person_preserving_negative_prompt(
                str(parameters.get("negativePrompt") or "")
            )
        try:
            result = self.adapter.generate(
                model=self.model,
                prompt=prompt,
                images=reference_images,
                parameters=parameters,
            )
        except Exception as error:
            raise self._provider_error(error) from error
        usage = dict(result.usage)
        if usage.get("cost_usd") is not None and usage.get("cost_usd_micros") is None:
            usage["cost_usd_micros"] = int(Decimal(str(usage["cost_usd"])) * 1_000_000)
        mime_type = (
            "image/png"
            if result.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/webp"
            if result.image_bytes.startswith(b"RIFF")
            else "image/jpeg"
        )
        return RenderResponse(
            result.image_bytes,
            mime_type,
            self.provider,
            self.model,
            self.region,
            result.request_id,
            1,
            usage,
        )

    def _provider_error(self, error: Exception) -> ProviderError:
        from apps.cost_lab_api.adapters import BFLUpstreamError

        if isinstance(error, ProviderError):
            return error
        status = getattr(error, "status_code", None)
        retryable = isinstance(error, BFLUpstreamError) and (
            status in {408, 409, 429, 500, 502, 503, 504}
            or getattr(error, "phase", "") in {"submit", "poll", "download", "timeout"}
        )
        message = str(error).upper()
        retryable = retryable or any(
            token in message
            for token in (
                "HTTP_408",
                "HTTP_409",
                "HTTP_429",
                "HTTP_500",
                "HTTP_502",
                "HTTP_503",
                "HTTP_504",
                "PROCESSING",
                "TIMED OUT",
                "TIMEOUT",
            )
        )
        code = str(error).split(":", 1)[0].strip().upper().replace(" ", "_")
        if not code or len(code) > 100:
            code = f"{self.provider}_REQUEST_FAILED"
        return ProviderError(code, retryable=retryable)


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def worker_concurrency(value: str | int | None = None) -> int:
    raw = value if value is not None else os.environ.get("WEARO_WORKER_CONCURRENCY", "4")
    try:
        concurrency = int(raw)
    except (TypeError, ValueError) as error:
        raise SystemExit("WEARO_WORKER_CONCURRENCY must be an integer from 1 to 32") from error
    if not 1 <= concurrency <= 32:
        raise SystemExit("WEARO_WORKER_CONCURRENCY must be between 1 and 32")
    return concurrency


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise SystemExit(f"{name} must be a positive integer") from error
    if value <= 0:
        raise SystemExit(f"{name} must be a positive integer")
    return value


class OpenAIImageOptions(TypedDict):
    streaming: bool
    connect_timeout_seconds: int
    read_timeout_seconds: int


def _openai_image_options() -> OpenAIImageOptions:
    return {
        "streaming": os.environ.get("OPENAI_IMAGE_STREAMING", "false").casefold() == "true",
        "connect_timeout_seconds": _positive_int_env("OPENAI_IMAGE_CONNECT_TIMEOUT", 15),
        "read_timeout_seconds": _positive_int_env("OPENAI_IMAGE_READ_TIMEOUT", 180),
    }


def build_worker(
    *, worker_slot: int | None = None, engine: Engine | None = None
) -> DurableRenderWorker:
    load_wearo_environment()
    database_url = _required("WEARO_DATABASE_URL")
    database_engine = engine or create_database_engine(
        database_url,
        application_name="wearo-render-worker",
        pool_size=1,
    )
    media = PostgresMediaRuntime(
        database_engine,
        private_blob_store_from_env(),
    )
    selected_provider = os.environ.get("WEARO_RENDER_PROVIDER", "GOOGLE_VERTEX").strip().upper()
    provider: WorkerProvider
    if selected_provider == "OPENAI":
        if os.environ.get("WEARO_OPENAI_ENABLED", "false").casefold() != "true":
            raise SystemExit("WEARO_OPENAI_ENABLED=true is required")
        openai_api_key = _required("WEARO_OPENAI_API_KEY")
        provider = OpenAIImageEditAdapter(
            RequestsMultipartTransport(),
            api_key=openai_api_key,
            model=os.environ.get("WEARO_OPENAI_MODEL", "gpt-image-2.5-sunburst"),
            **_openai_image_options(),
        )
    elif selected_provider == "GOOGLE_VERTEX":
        if os.environ.get("WEARO_VERTEX_ENABLED", "false").casefold() != "true":
            raise SystemExit("WEARO_VERTEX_ENABLED=true is required")
        provider = VertexTryOnAdapter(
            RequestsJsonTransport(),
            GoogleDefaultAccessTokenProvider(),
            project_id=_required("WEARO_VERTEX_PROJECT_ID"),
            region=os.environ.get("WEARO_VERTEX_REGION", "asia-southeast1"),
        )
    elif selected_provider == "BYTEPLUS":
        if os.environ.get("WEARO_BYTEPLUS_ENABLED", "false").casefold() != "true":
            raise SystemExit("WEARO_BYTEPLUS_ENABLED=true is required")
        provider = BytePlusImageGenerationAdapter(
            RequestsJsonTransport(),
            api_key=_required("WEARO_BYTEPLUS_API_KEY"),
            model=_required("WEARO_BYTEPLUS_MODEL"),
            region=os.environ.get("WEARO_BYTEPLUS_REGION", "ap-southeast-1"),
        )
    else:
        raise SystemExit("WEARO_RENDER_PROVIDER must be OPENAI, GOOGLE_VERTEX, or BYTEPLUS")
    analysis_endpoint = os.environ.get("WEARO_ANALYSIS_ENDPOINT", "")
    analysis_token = os.environ.get("WEARO_ANALYSIS_TOKEN", "")
    analyzer: QualityAnalyzer
    if analysis_endpoint and analysis_token:
        analyzer = HttpAnalysisClient(analysis_endpoint, bearer_token=analysis_token)
    elif selected_provider == "OPENAI":
        analyzer = OpenAIAnalysisClient(
            api_key=openai_api_key,
            model=os.environ.get("WEARO_OPENAI_ANALYSIS_MODEL", "gpt-6-luna"),
        )
    else:
        raise SystemExit(
            "WEARO_ANALYSIS_ENDPOINT and WEARO_ANALYSIS_TOKEN are required for this provider"
        )
    worker_id = os.environ.get("WEARO_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    if worker_slot is not None:
        worker_id = f"{worker_id}-{worker_slot}"

    def resolve_provider(job: DurableRenderJob) -> WorkerProvider:
        release_id = job.ordered_routes[0].release_id
        if release_id is not None:
            with database_engine.connect() as connection:
                promoted_route = (
                    connection.execute(
                        text("""SELECT
                            p.provider_type,
                            p.api_base_url,
                            p.secret_ciphertext,
                            p.secret_reference,
                            m.api_identifier,
                            quality.settings quality_settings,
                            mapping.request_parameters,
                            mapping.provider_quality
                          FROM cost_lab.production_model_releases release
                          JOIN cost_lab.ai_models m USING (model_id)
                          JOIN cost_lab.model_providers p USING (provider_id)
                          LEFT JOIN cost_lab.quality_profiles quality ON quality.code='HIGH'
                          LEFT JOIN cost_lab.model_quality_mapping mapping
                            ON mapping.model_id=m.model_id
                           AND mapping.profile_id=quality.profile_id
                           AND mapping.supported
                          WHERE release.release_id=:release
                            AND release.retired_at IS NULL
                            AND release.approved_quality_levels ? 'HIGH'
                            AND m.enabled AND p.enabled"""),
                        {"release": release_id},
                    )
                    .mappings()
                    .one_or_none()
                )
            if promoted_route is None or promoted_route["api_identifier"] != job.model:
                raise ProviderError("PROVIDER_ROUTE_UNAVAILABLE", retryable=False)
            provider_type = str(promoted_route["provider_type"])
            base_url = str(promoted_route["api_base_url"] or "").strip()
            if provider_type == "SECRET_REFERENCE" and "bfl.ai" in base_url.casefold():
                provider_type = "BFL"
            if provider_type != job.provider or not base_url:
                raise ProviderError("PROVIDER_ROUTE_UNAVAILABLE", retryable=False)
            reference = str(promoted_route["secret_reference"] or "")
            credential = ""
            if reference.startswith("env:"):
                credential = os.environ.get(reference[4:], "")
            elif promoted_route["secret_ciphertext"] is not None:
                encryption_key = os.environ.get("COST_LAB_ENCRYPTION_KEY", "")
                if encryption_key:
                    try:
                        credential = (
                            Fernet(encryption_key.encode())
                            .decrypt(bytes(promoted_route["secret_ciphertext"]))
                            .decode()
                        )
                    except (InvalidToken, ValueError):
                        credential = ""
            if not credential:
                raise ProviderError("PROVIDER_CREDENTIAL_UNAVAILABLE", retryable=False)
            request_parameters = dict(promoted_route["quality_settings"] or {}) | dict(
                promoted_route["request_parameters"] or {}
            )
            if promoted_route["provider_quality"]:
                request_parameters["quality"] = promoted_route["provider_quality"]
            return _CostLabProductionAdapter(
                provider=provider_type,
                model=job.model,
                region=job.region,
                base_url=base_url,
                api_key=credential,
                request_parameters=request_parameters,
            )
        with database_engine.connect() as connection:
            route = (
                connection.execute(
                    text("""SELECT p.adapter_type, p.credential_env_name
                  FROM ai_models m JOIN ai_providers p USING (provider_id)
                  WHERE p.code=:provider AND m.api_model_id=:model AND m.region=:region"""),
                    {"provider": job.provider, "model": job.model, "region": job.region},
                )
                .mappings()
                .one_or_none()
            )
        if route is None:
            raise ProviderError("PROVIDER_ROUTE_UNAVAILABLE", retryable=False)
        credential = os.environ.get(str(route["credential_env_name"]), "")
        if not credential:
            raise ProviderError("PROVIDER_CREDENTIAL_UNAVAILABLE", retryable=False)
        if route["adapter_type"] == "OPENAI":
            return OpenAIImageEditAdapter(
                RequestsMultipartTransport(),
                api_key=credential,
                model=job.model,
                **_openai_image_options(),
            )
        if route["adapter_type"] == "GOOGLE_VERTEX":
            return VertexTryOnAdapter(
                RequestsJsonTransport(),
                GoogleDefaultAccessTokenProvider(),
                project_id=credential,
                region=job.region,
            )
        if route["adapter_type"] == "BYTEPLUS":
            return BytePlusImageGenerationAdapter(
                RequestsJsonTransport(), api_key=credential, model=job.model, region=job.region
            )
        raise ProviderError("PROVIDER_ADAPTER_UNSUPPORTED", retryable=False)

    return DurableRenderWorker(
        PostgresRenderRuntime(
            database_engine,
            enforce_free_allowance=(
                os.environ.get(
                    "WEARO_FREE_TRYON_LIMIT_ENABLED",
                    os.environ.get("WEARO_DAILY_LIMIT_ENABLED", "true"),
                ).casefold()
                == "true"
            ),
        ),
        media,
        provider,
        RenderQualityGate(analyzer),
        worker_id=worker_id,
        enforce_quality_gate=(
            os.environ.get("WEARO_RENDER_QUALITY_GATE_ENABLED", "true").casefold() == "true"
        ),
        provider_resolver=resolve_provider,
    )


def build_drive_worker(
    *, worker_slot: int | None = None, engine: Engine | None = None
) -> DriveSyncWorker | None:
    load_wearo_environment()
    config = GoogleDriveConfig.from_env()
    if config is None:
        return None
    database_engine = engine or create_database_engine(
        _required("WEARO_DATABASE_URL"),
        application_name="wearo-drive-worker",
        pool_size=1,
    )
    media = PostgresMediaRuntime(database_engine, private_blob_store_from_env())
    worker_id = os.environ.get("WEARO_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    if worker_slot is not None:
        worker_id = f"{worker_id}-{worker_slot}"
    return DriveSyncWorker(
        database_engine,
        GoogleDriveService(database_engine, config),
        media,
        worker_id=f"{worker_id}-drive",
    )


def main() -> None:
    load_wearo_environment()
    parser = argparse.ArgumentParser(description="Wearo durable render worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--concurrency", type=int)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 30:
        raise SystemExit("--poll-seconds must be between 0.1 and 30")
    concurrency = worker_concurrency(args.concurrency)
    stop = threading.Event()
    engine = create_database_engine(
        _required("WEARO_DATABASE_URL"),
        application_name=f"wearo-render-worker:{socket.gethostname()}:{os.getpid()}",
        pool_size=concurrency,
    )
    health_server = (
        None
        if args.once
        else start_worker_health_server(
            "render-worker", int(os.environ.get("WEARO_RENDER_WORKER_HEALTH_PORT", "8021"))
        )
    )

    def run_slot(slot: int) -> None:
        worker = build_worker(worker_slot=slot, engine=engine)
        drive_worker = build_drive_worker(worker_slot=slot, engine=engine)
        while not stop.is_set():
            try:
                recovery = worker.recover_stale()
                outcome = worker.run_once()
                drive_recovered = drive_worker.recover_expired() if drive_worker else 0
                drive_claimed = drive_worker.run_once() if drive_worker else False
            except SQLAlchemyError:
                if args.once:
                    raise
                LOGGER.exception(
                    "Database operation failed in render worker slot %s; retrying", slot
                )
                stop.wait(max(args.poll_seconds, 2.0))
                continue
            if args.once:
                print(
                    f"slot={slot} timed_out={recovery.failed} "
                    f"claimed={str(outcome.claimed).lower()} "
                    f"drive_recovered={drive_recovered} "
                    f"drive_claimed={str(drive_claimed).lower()}"
                )
                return
            if not outcome.claimed and not drive_claimed:
                stop.wait(args.poll_seconds)

    threads = [
        threading.Thread(target=run_slot, args=(slot,), name=f"wearo-render-worker-{slot}")
        for slot in range(1, concurrency + 1)
    ]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        stop.set()
        for thread in threads:
            thread.join()
    finally:
        if health_server is not None:
            health_server.shutdown()
        engine.dispose()


if __name__ == "__main__":
    main()
