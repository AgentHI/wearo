from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from .external_runtime import AnalysisServiceError
from .image_inputs import InputRole
from .image_watermark import ImageWatermarkError, apply_generated_image_watermark
from .render_provider import ProviderError, RenderRequest, RenderResponse
from .render_quality import QualityDecision
from .render_runtime import DurableRenderJob, LeasedRenderWork, RecoverySummary


class WorkerRuntime(Protocol):
    def claim_next(
        self, worker_id: str, *, now: datetime | None = None
    ) -> LeasedRenderWork | None: ...

    def complete_success(
        self,
        *,
        job_id: UUID,
        result_asset_id: UUID,
        provider_request_id: str,
        quality_details: dict[str, object],
        provider_usage: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> DurableRenderJob: ...

    def complete_failure(
        self, job_id: UUID, error_code: str, *, now: datetime | None = None
    ) -> DurableRenderJob: ...

    def recover_expired(self, *, now: datetime | None = None) -> RecoverySummary: ...


class WorkerMedia(Protocol):
    def read_prepared(
        self, asset_id: UUID, account_id: UUID, role: InputRole
    ) -> tuple[bytes, str]: ...
    def store_result(self, account_id: UUID, content: bytes, content_type: str) -> UUID: ...
    def store_progressive_preview(self, job_id: UUID, content: bytes) -> None: ...
    def clear_progressive_preview(self, job_id: UUID) -> None: ...


class WorkerProvider(Protocol):
    provider: str
    model: str
    region: str

    def render(self, request: RenderRequest) -> RenderResponse: ...


class WorkerQualityGate(Protocol):
    def evaluate(self, person: bytes, item: bytes, result: bytes) -> QualityDecision: ...


@dataclass(frozen=True)
class WorkerOutcome:
    claimed: bool
    job: DurableRenderJob | None


class DurableRenderWorker:
    def __init__(
        self,
        runtime: WorkerRuntime,
        media: WorkerMedia,
        provider: WorkerProvider,
        quality: WorkerQualityGate,
        *,
        worker_id: str,
        enforce_quality_gate: bool = True,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker identity is required")
        self.runtime = runtime
        self.media = media
        self.provider = provider
        self.quality = quality
        self.worker_id = worker_id
        self.enforce_quality_gate = enforce_quality_gate

    def recover_stale(self, *, now: datetime | None = None) -> RecoverySummary:
        return self.runtime.recover_expired(now=now)

    def run_once(self, *, now: datetime | None = None) -> WorkerOutcome:
        current = now or datetime.now(UTC)
        work = self.runtime.claim_next(self.worker_id, now=current)
        if work is None:
            return WorkerOutcome(False, None)
        job = work.job
        try:
            configured_route = (self.provider.provider, self.provider.model, self.provider.region)
            quoted_route = (job.provider, job.model, job.region)
            if configured_route != quoted_route:
                failed = self.runtime.complete_failure(
                    job.job_id,
                    "PROVIDER_ROUTE_MISMATCH",
                    now=current,
                )
                return WorkerOutcome(True, failed)
            person, person_mime = self.media.read_prepared(
                job.person_asset_id, job.account_id, "PERSON"
            )
            item, item_mime = self.media.read_prepared(job.item_asset_id, job.account_id, "GARMENT")
            response = self.provider.render(
                RenderRequest(
                    person,
                    item,
                    person_mime,
                    item_mime,
                    "APPAREL",
                    on_partial=lambda image, mime, _index: self.media.store_progressive_preview(
                        job.job_id,
                        apply_generated_image_watermark(
                            image, mime, company_name=job.company_name
                        )[0],
                    ),
                )
            )
            quality_bypassed = not self.enforce_quality_gate
            decision = (
                self.quality.evaluate(person, item, response.image)
                if self.enforce_quality_gate
                else QualityDecision(True, False, ())
            )
            if not decision.accepted:
                self.media.clear_progressive_preview(job.job_id)
                failed = self.runtime.complete_failure(
                    job.job_id,
                    "QUALITY_REJECTED",
                    now=current,
                )
                return WorkerOutcome(True, failed)
            watermarked, watermarked_type = apply_generated_image_watermark(
                response.image, response.mime_type, company_name=job.company_name
            )
            result_asset_id = self.media.store_result(
                job.account_id, watermarked, watermarked_type
            )
            delivered = self.runtime.complete_success(
                job_id=job.job_id,
                result_asset_id=result_asset_id,
                provider_request_id=response.request_id or "unavailable",
                provider_usage=response.usage,
                quality_details={
                    "accepted": decision.accepted,
                    "hard_failure": decision.hard_failure,
                    "reasons": list(decision.reasons),
                    "bypassed": quality_bypassed,
                },
                now=current,
            )
            self.media.clear_progressive_preview(job.job_id)
            return WorkerOutcome(True, delivered)
        except ProviderError as error:
            self.media.clear_progressive_preview(job.job_id)
            failed = self.runtime.complete_failure(job.job_id, error.code, now=current)
            return WorkerOutcome(True, failed)
        except AnalysisServiceError:
            self.media.clear_progressive_preview(job.job_id)
            failed = self.runtime.complete_failure(job.job_id, "ANALYSIS_UNAVAILABLE", now=current)
            return WorkerOutcome(True, failed)
        except ImageWatermarkError:
            self.media.clear_progressive_preview(job.job_id)
            failed = self.runtime.complete_failure(job.job_id, "WATERMARK_FAILED", now=current)
            return WorkerOutcome(True, failed)
