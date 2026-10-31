from __future__ import annotations

import argparse
import os
import socket
import time
from pathlib import Path

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
from .render_provider import OpenAIImageEditAdapter, VertexTryOnAdapter
from .render_quality import QualityAnalyzer, RenderQualityGate
from .render_runtime import DurableRenderJob, PostgresRenderRuntime


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def build_worker() -> DurableRenderWorker:
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
    else:
        raise SystemExit("WEARO_RENDER_PROVIDER must be OPENAI or GOOGLE_VERTEX")
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
            "WEARO_ANALYSIS_ENDPOINT and WEARO_ANALYSIS_TOKEN are required for Google Vertex"
        )
    worker_id = os.environ.get("WEARO_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"

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
            raise SystemExit("Quoted model is not configured in AI Models & Cost")
        credential = _required(str(route["credential_env_name"]))
        if route["adapter_type"] == "OPENAI":
            return OpenAIImageEditAdapter(
                RequestsMultipartTransport(), api_key=credential, model=job.model
            )
        if route["adapter_type"] == "GOOGLE_VERTEX":
            return VertexTryOnAdapter(
                RequestsJsonTransport(),
                GoogleDefaultAccessTokenProvider(),
                project_id=credential,
                region=job.region,
            )
        raise SystemExit("Selected model uses an unsupported provider adapter")

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
    parser = argparse.ArgumentParser(description="Wearo durable render worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 30:
        raise SystemExit("--poll-seconds must be between 0.1 and 30")
    worker = build_worker()
    while True:
        recovery = worker.recover_stale()
        outcome = worker.run_once()
        if args.once:
            print(f"timed_out={recovery.failed} claimed={str(outcome.claimed).lower()}")
            return
        if not outcome.claimed:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
