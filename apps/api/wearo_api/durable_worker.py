from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from .external_runtime import AnalysisServiceError
from .image_inputs import InputRole
from .image_watermark import ImageWatermarkError, apply_generated_image_watermark
from .render_provider import ProviderError, RenderRequest, RenderResponse
from .render_quality import QualityDecision
from .render_runtime import DurableRenderJob, LeasedRenderWork, RecoverySummary

logger = logging.getLogger(__name__)


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
        provider: str | None = None,
        model: str | None = None,
        region: str | None = None,
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
        provider_resolver: Callable[[DurableRenderJob], WorkerProvider] | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker identity is required")
        self.runtime = runtime
        self.media = media
        self.provider = provider
        self.quality = quality
        self.worker_id = worker_id
        self.enforce_quality_gate = enforce_quality_gate
        self.provider_resolver = provider_resolver

    def recover_stale(self, *, now: datetime | None = None) -> RecoverySummary:
        return self.runtime.recover_expired(now=now)

    def _clear_progressive_preview(self, job_id: UUID) -> None:
        try:
            self.media.clear_progressive_preview(job_id)
        except Exception as error:
            logger.warning(
                "Render preview cleanup failed job_id=%s error_type=%s",
                job_id,
                type(error).__name__,
                exc_info=True,
            )

    def run_once(self, *, now: datetime | None = None) -> WorkerOutcome:
        current = now or datetime.now(UTC)
        work = self.runtime.claim_next(self.worker_id, now=current)
        if work is None:
            return WorkerOutcome(False, None)
        job = work.job
        try:
            person, person_mime = self.media.read_prepared(
                job.person_asset_id, job.account_id, "PERSON"
            )
            item, item_mime = self.media.read_prepared(job.item_asset_id, job.account_id, "GARMENT")
            response: RenderResponse | None = None
            selected_route = None
            routes = job.ordered_routes
            for index, route in enumerate(routes):
                candidate_job = replace(
                    job,
                    provider=route.provider,
                    model=route.model,
                    region=route.region,
                    route_candidates=(route,),
                )
                try:
                    provider = (
                        self.provider_resolver(candidate_job)
                        if self.provider_resolver
                        else self.provider
                    )
                    configured_route = (provider.provider, provider.model, provider.region)
                    candidate_route = (route.provider, route.model, route.region)
                    if configured_route != candidate_route:
                        raise ProviderError("PROVIDER_ROUTE_MISMATCH", retryable=False)
                    response = provider.render(
                        RenderRequest(
                            person,
                            item,
                            person_mime,
                            item_mime,
                            "APPAREL",
                            on_partial=lambda image, mime, _index: (
                                self.media.store_progressive_preview(
                                    job.job_id,
                                    apply_generated_image_watermark(
                                        image, mime, company_name=job.company_name
                                    )[0],
                                )
                            ),
                            job_id=str(job.job_id),
                            product_kind=job.product_kind,
                        )
                    )
                    selected_route = route
                    break
                except ProviderError as error:
                    request_invalid = error.code in {
                        "CAPABILITY_UNSUPPORTED",
                        "PROVIDER_IMAGE_INVALID",
                        "PROVIDER_IMAGE_TOO_LARGE",
                        "CONTENT_MODERATED",
                        "SAFETY_REJECTED",
                    } or any(
                        marker in error.code.upper()
                        for marker in ("MODERAT", "SAFETY", "NSFW", "CONTENT_POLICY")
                    )
                    has_fallback = index + 1 < len(routes)
                    if has_fallback and not request_invalid:
                        logger.warning(
                            "Render provider failed; trying fallback job_id=%s priority=%s "
                            "provider=%s model=%s error=%s next_priority=%s",
                            job.job_id,
                            route.priority,
                            route.provider,
                            route.model,
                            error.code,
                            routes[index + 1].priority,
                        )
                        continue
                    failed = self.runtime.complete_failure(job.job_id, error.code, now=current)
                    self._clear_progressive_preview(job.job_id)
                    return WorkerOutcome(True, failed)
            if response is None or selected_route is None:  # pragma: no cover - loop is exhaustive.
                failed = self.runtime.complete_failure(
                    job.job_id, "PROVIDER_ROUTE_UNAVAILABLE", now=current
                )
                self._clear_progressive_preview(job.job_id)
                return WorkerOutcome(True, failed)
            quality_bypassed = not self.enforce_quality_gate
            decision = (
                self.quality.evaluate(person, item, response.image)
                if self.enforce_quality_gate
                else QualityDecision(True, False, ())
            )
            if not decision.accepted:
                failed = self.runtime.complete_failure(
                    job.job_id,
                    "QUALITY_REJECTED",
                    now=current,
                )
                self._clear_progressive_preview(job.job_id)
                return WorkerOutcome(True, failed)
            watermarked, watermarked_type = apply_generated_image_watermark(
                response.image, response.mime_type, company_name=job.company_name
            )
            result_asset_id = self.media.store_result(job.account_id, watermarked, watermarked_type)
            delivered = self.runtime.complete_success(
                job_id=job.job_id,
                result_asset_id=result_asset_id,
                provider_request_id=response.request_id or "unavailable",
                provider_usage=response.usage,
                provider=selected_route.provider,
                model=selected_route.model,
                region=selected_route.region,
                quality_details={
                    "accepted": decision.accepted,
                    "hard_failure": decision.hard_failure,
                    "reasons": list(decision.reasons),
                    "bypassed": quality_bypassed,
                },
                now=current,
            )
            self._clear_progressive_preview(job.job_id)
            return WorkerOutcome(True, delivered)
        except AnalysisServiceError:
            failed = self.runtime.complete_failure(job.job_id, "ANALYSIS_UNAVAILABLE", now=current)
            self._clear_progressive_preview(job.job_id)
            return WorkerOutcome(True, failed)
        except ImageWatermarkError:
            failed = self.runtime.complete_failure(job.job_id, "WATERMARK_FAILED", now=current)
            self._clear_progressive_preview(job.job_id)
            return WorkerOutcome(True, failed)
