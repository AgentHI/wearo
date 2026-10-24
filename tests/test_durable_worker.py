from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from apps.api.wearo_api.durable_worker import DurableRenderWorker
from apps.api.wearo_api.image_inputs import InputRole
from apps.api.wearo_api.render_provider import ProviderError, RenderRequest, RenderResponse
from apps.api.wearo_api.render_quality import QualityDecision
from apps.api.wearo_api.render_runtime import DurableRenderJob, LeasedRenderWork, RecoverySummary

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class Runtime:
    def __init__(self, job: DurableRenderJob | None) -> None:
        self.job = job
        self.quality_details: dict[str, object] | None = None

    def claim_next(self, worker_id: str, *, now: datetime | None = None) -> LeasedRenderWork | None:
        if self.job is None:
            return None
        claimed = replace(self.job, status="PROCESSING")
        self.job = claimed
        return LeasedRenderWork(uuid4(), claimed, 1, NOW + timedelta(minutes=3))

    def complete_success(
        self,
        *,
        job_id: UUID,
        result_asset_id: UUID,
        provider_request_id: str,
        quality_details: dict[str, object],
        provider_usage: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> DurableRenderJob:
        assert self.job is not None and quality_details["accepted"] is True
        self.quality_details = quality_details
        self.job = replace(
            self.job,
            status="DELIVERED",
            result_asset_id=result_asset_id,
            provider_request_id=provider_request_id,
        )
        return self.job

    def complete_failure(
        self, job_id: UUID, error_code: str, *, now: datetime | None = None
    ) -> DurableRenderJob:
        assert self.job is not None
        self.job = replace(self.job, status="FAILED", error_code=error_code)
        return self.job

    def recover_expired(self, *, now: datetime | None = None) -> RecoverySummary:
        return RecoverySummary(0, 0)


class Media:
    def __init__(self) -> None:
        self.result_id = uuid4()
        self.partials: list[bytes] = []
        self.cleared: list[UUID] = []

    def read_prepared(self, asset_id: UUID, account_id: UUID, role: InputRole) -> tuple[bytes, str]:
        return asset_id.bytes, "image/png"

    def store_result(self, account_id: UUID, content: bytes, content_type: str) -> UUID:
        assert content == b"result" and content_type == "image/png"
        return self.result_id

    def store_progressive_preview(self, job_id: UUID, content: bytes) -> None:
        self.partials.append(content)

    def clear_progressive_preview(self, job_id: UUID) -> None:
        self.cleared.append(job_id)


class Provider:
    provider = "GOOGLE_VERTEX"
    model = "virtual-try-on-001"
    region = "asia-southeast1"

    def __init__(self, error: ProviderError | None = None) -> None:
        self.error = error

    def render(self, request: RenderRequest) -> RenderResponse:
        if self.error is not None:
            raise self.error
        if request.on_partial is not None:
            request.on_partial(b"partial", "image/png", 0)
        return RenderResponse(
            b"result",
            "image/png",
            "GOOGLE_VERTEX",
            "virtual-try-on-001",
            "asia-southeast1",
            "request-1",
            1,
        )


class Quality:
    def __init__(self, accepted: bool) -> None:
        self.accepted = accepted
        self.calls = 0

    def evaluate(self, person: bytes, item: bytes, result: bytes) -> QualityDecision:
        self.calls += 1
        return QualityDecision(
            self.accepted,
            not self.accepted,
            () if self.accepted else ("IDENTITY_CHANGED",),
        )


def job() -> DurableRenderJob:
    return DurableRenderJob(
        uuid4(), uuid4(), uuid4(), uuid4(), "PENDING", uuid4(), uuid4(), None, None, None
    )


def test_no_work_is_a_safe_noop() -> None:
    result = DurableRenderWorker(
        Runtime(None), Media(), Provider(), Quality(True), worker_id="worker-1"
    ).run_once(now=NOW)
    assert result.claimed is False and result.job is None


def test_accepted_result_is_privately_stored_and_settled() -> None:
    runtime, media = Runtime(job()), Media()
    result = DurableRenderWorker(
        runtime, media, Provider(), Quality(True), worker_id="worker-1"
    ).run_once(now=NOW)
    assert result.job is not None
    assert result.job.status == "DELIVERED"
    assert result.job.result_asset_id == media.result_id
    assert media.partials == [b"partial"] and media.cleared == [result.job.job_id]


def test_quality_and_provider_failures_are_terminal_without_publication() -> None:
    for provider, quality, expected in (
        (Provider(), Quality(False), "QUALITY_REJECTED"),
        (
            Provider(ProviderError("VERTEX_HTTP_503", retryable=True)),
            Quality(True),
            "VERTEX_HTTP_503",
        ),
    ):
        runtime = Runtime(job())
        result = DurableRenderWorker(
            runtime, Media(), provider, quality, worker_id="worker-1"
        ).run_once(now=NOW)
        assert result.job is not None
        assert result.job.status == "FAILED" and result.job.error_code == expected


def test_quality_gate_can_be_bypassed_without_calling_analyzer() -> None:
    runtime, media, quality = Runtime(job()), Media(), Quality(False)
    result = DurableRenderWorker(
        runtime,
        media,
        Provider(),
        quality,
        worker_id="worker-1",
        enforce_quality_gate=False,
    ).run_once(now=NOW)
    assert result.job is not None and result.job.status == "DELIVERED"
    assert quality.calls == 0
    assert runtime.quality_details == {
        "accepted": True,
        "hard_failure": False,
        "reasons": [],
        "bypassed": True,
    }


def test_quoted_provider_route_must_match_worker_before_media_or_provider_call() -> None:
    mismatched = replace(job(), provider="OPENAI", model="gpt-image-2.5-sunburst", region="global")
    runtime = Runtime(mismatched)
    result = DurableRenderWorker(
        runtime, Media(), Provider(), Quality(True), worker_id="worker-1"
    ).run_once(now=NOW)
    assert result.job is not None
    assert result.job.status == "FAILED"
    assert result.job.error_code == "PROVIDER_ROUTE_MISMATCH"
