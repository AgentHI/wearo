from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from .render_preflight import BetaRenderQuote
from .render_provider import ProviderError, RenderRequest, RenderResponse
from .render_quality import QualityDecision


class RenderCommandError(ValueError):
    pass


@dataclass(frozen=True)
class RenderJob:
    job_id: UUID
    quote_id: UUID
    account_id: UUID
    principal_id: UUID
    idempotency_key: str
    state: str
    person_asset_id: UUID
    item_asset_id: UUID
    result_asset_id: UUID | None = None
    failure_code: str | None = None
    provider_request_id: str | None = None
    quality_reasons: tuple[str, ...] = ()


class JobStore(Protocol):
    def by_idempotency(self, account_id: UUID, key: str) -> RenderJob | None: ...
    def create_if_absent(self, job: RenderJob) -> tuple[RenderJob, bool]: ...
    def get(self, job_id: UUID) -> RenderJob | None: ...
    def transition(self, job_id: UUID, expected: str, updated: RenderJob) -> bool: ...


class WorkQueue(Protocol):
    def enqueue(self, job_id: UUID) -> None: ...


class QuotaCoordinator(Protocol):
    def reserve(self, account_id: UUID, job_id: UUID, *, now: datetime) -> object: ...
    def settle_success(self, account_id: UUID, job_id: UUID, *, now: datetime) -> object: ...
    def release_failure(self, account_id: UUID, job_id: UUID, *, now: datetime) -> object: ...


class MediaReader(Protocol):
    def read_owned(self, asset_id: UUID, account_id: UUID) -> tuple[bytes, str]: ...


class Provider(Protocol):
    def render(self, request: RenderRequest) -> RenderResponse: ...


class QualityGate(Protocol):
    def evaluate(self, person: bytes, item: bytes, result: bytes) -> QualityDecision: ...


class ResultPublisher(Protocol):
    def store_result(self, account_id: UUID, content: bytes, content_type: str) -> UUID: ...


class RenderCommandService:
    def __init__(self, jobs: JobStore, queue: WorkQueue, quota: QuotaCoordinator) -> None:
        self.jobs, self.queue, self.quota = jobs, queue, quota

    def create(
        self,
        quote: BetaRenderQuote,
        *,
        account_id: UUID,
        principal_id: UUID,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> RenderJob:
        current = now or datetime.now(UTC)
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise RenderCommandError("valid idempotency key is required")
        if (
            quote.account_id != account_id
            or quote.principal_id != principal_id
            or quote.expires_at <= current
        ):
            raise RenderCommandError("quote unavailable")
        existing = self.jobs.by_idempotency(account_id, idempotency_key)
        if existing is not None:
            return existing
        job = RenderJob(
            uuid4(),
            quote.quote_id,
            account_id,
            principal_id,
            idempotency_key,
            "QUEUED",
            quote.person_asset_id,
            quote.item_asset_id,
        )
        self.quota.reserve(account_id, job.job_id, now=current)
        canonical, created = self.jobs.create_if_absent(job)
        if not created:
            self.quota.release_failure(account_id, job.job_id, now=current)
            return canonical
        self.queue.enqueue(job.job_id)
        return job


class RenderWorker:
    def __init__(
        self,
        jobs: JobStore,
        media: MediaReader,
        provider: Provider,
        quality: QualityGate,
        results: ResultPublisher,
        quota: QuotaCoordinator,
    ) -> None:
        self.jobs, self.media, self.provider = jobs, media, provider
        self.quality, self.results, self.quota = quality, results, quota

    def execute(self, job_id: UUID, *, now: datetime | None = None) -> RenderJob:
        current = now or datetime.now(UTC)
        job = self.jobs.get(job_id)
        if job is None:
            raise RenderCommandError("job unavailable")
        if job.state in {"DELIVERED", "FAILED"}:
            return job
        processing = replace(job, state="PROCESSING")
        if not self.jobs.transition(job_id, "QUEUED", processing):
            latest = self.jobs.get(job_id)
            if latest is None:
                raise RenderCommandError("job unavailable")
            return latest
        try:
            person, person_mime = self.media.read_owned(job.person_asset_id, job.account_id)
            item, item_mime = self.media.read_owned(job.item_asset_id, job.account_id)
            response = self.provider.render(
                RenderRequest(person, item, person_mime, item_mime, "APPAREL")
            )
            decision = self.quality.evaluate(person, item, response.image)
            if not decision.accepted:
                return self._fail(processing, "QUALITY_REJECTED", decision.reasons, current)
            result_id = self.results.store_result(
                job.account_id, response.image, response.mime_type
            )
            delivered = replace(
                processing,
                state="DELIVERED",
                result_asset_id=result_id,
                provider_request_id=response.request_id,
            )
            if not self.jobs.transition(job_id, "PROCESSING", delivered):
                raise RenderCommandError("job transition conflict")
            self.quota.settle_success(job.account_id, job.job_id, now=current)
            return delivered
        except ProviderError as error:
            return self._fail(processing, error.code, (), current)

    def _fail(
        self, job: RenderJob, code: str, reasons: tuple[str, ...], now: datetime
    ) -> RenderJob:
        failed = replace(job, state="FAILED", failure_code=code, quality_reasons=reasons)
        if not self.jobs.transition(job.job_id, "PROCESSING", failed):
            raise RenderCommandError("job transition conflict")
        self.quota.release_failure(job.account_id, job.job_id, now=now)
        return failed
