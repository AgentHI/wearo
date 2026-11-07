from __future__ import annotations

import argparse
import os
import socket
import threading
from pathlib import Path
from typing import TypedDict

from sqlalchemy import create_engine, text

from .database import normalize_database_url
from .durable_worker import DurableRenderWorker, WorkerProvider
from .environment import load_wearo_environment
from .external_runtime import (
    GoogleDefaultAccessTokenProvider,
    HttpAnalysisClient,
    OpenAIAnalysisClient,
    RequestsJsonTransport,
    RequestsMultipartTransport,
)
from .media_runtime import FilesystemPrivateBlobStore, PostgresMediaRuntime
from .render_provider import (
    BytePlusImageGenerationAdapter,
    OpenAIImageEditAdapter,
    ProviderError,
    VertexTryOnAdapter,
)
from .render_quality import QualityAnalyzer, RenderQualityGate
from .render_runtime import DurableRenderJob, PostgresRenderRuntime


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


def build_worker(*, worker_slot: int | None = None) -> DurableRenderWorker:
    load_wearo_environment()
    database_url = _required("WEARO_DATABASE_URL")
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    media = PostgresMediaRuntime(
        engine,
        FilesystemPrivateBlobStore(
            Path(os.environ.get("WEARO_PRIVATE_STORAGE_ROOT", ".wearo-storage"))
        ),
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
        with engine.connect() as connection:
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
            engine,
            enforce_daily_allowance=(
                os.environ.get("WEARO_DAILY_LIMIT_ENABLED", "true").casefold() == "true"
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

    def run_slot(slot: int) -> None:
        worker = build_worker(worker_slot=slot)
        while not stop.is_set():
            recovery = worker.recover_stale()
            outcome = worker.run_once()
            if args.once:
                print(
                    f"slot={slot} timed_out={recovery.failed} "
                    f"claimed={str(outcome.claimed).lower()}"
                )
                return
            if not outcome.claimed:
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


if __name__ == "__main__":
    main()
