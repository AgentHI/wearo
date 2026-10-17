from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from apps.api.wearo_api.render_execution import RenderCommandService, RenderJob, RenderWorker
from apps.api.wearo_api.render_preflight import BetaRenderQuote, ModelRoute
from apps.api.wearo_api.render_provider import RenderResponse
from apps.api.wearo_api.render_quality import QualityDecision

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class Jobs:
    def __init__(self) -> None:
        self.items: dict[UUID, RenderJob] = {}

    def by_idempotency(self, account_id: UUID, key: str) -> RenderJob | None:
        return next(
            (
                j
                for j in self.items.values()
                if j.account_id == account_id and j.idempotency_key == key
            ),
            None,
        )

    def create_if_absent(self, job: RenderJob) -> tuple[RenderJob, bool]:
        existing = self.by_idempotency(job.account_id, job.idempotency_key)
        if existing:
            return existing, False
        self.items[job.job_id] = job
        return job, True

    def get(self, job_id: UUID) -> RenderJob | None:
        return self.items.get(job_id)

    def transition(self, job_id: UUID, expected: str, updated: RenderJob) -> bool:
        current = self.items.get(job_id)
        if current is None or current.state != expected:
            return False
        self.items[job_id] = updated
        return True


class Queue:
    def __init__(self) -> None:
        self.ids: list[UUID] = []

    def enqueue(self, job_id: UUID) -> None:
        self.ids.append(job_id)


class Quota:
    def __init__(self) -> None:
        self.active: set[UUID] = set()
        self.successes = 0

    def reserve(self, account_id: UUID, job_id: UUID, *, now: datetime) -> object:
        self.active.add(job_id)
        return object()

    def settle_success(self, account_id: UUID, job_id: UUID, *, now: datetime) -> object:
        self.active.remove(job_id)
        self.successes += 1
        return object()

    def release_failure(self, account_id: UUID, job_id: UUID, *, now: datetime) -> object:
        self.active.discard(job_id)
        return object()


class Media:
    def read_owned(self, asset_id: UUID, account_id: UUID) -> tuple[bytes, str]:
        return (str(asset_id).encode(), "image/png")


class Provider:
    def render(self, request: object) -> RenderResponse:
        return RenderResponse(
            b"result",
            "image/png",
            "GOOGLE_VERTEX",
            "virtual-try-on-001",
            "asia-southeast1",
            "req-1",
            1,
        )


class Quality:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted

    def evaluate(self, person: bytes, item: bytes, result: bytes) -> QualityDecision:
        return QualityDecision(
            self.accepted, not self.accepted, () if self.accepted else ("PRODUCT_CHANGED",)
        )


class Results:
    def __init__(self) -> None:
        self.ids: list[UUID] = []

    def store_result(self, account_id: UUID, content: bytes, content_type: str) -> UUID:
        self.ids.append(uuid4())
        return self.ids[-1]


def quote(account: UUID, principal: UUID) -> BetaRenderQuote:
    return BetaRenderQuote(
        uuid4(),
        account,
        principal,
        uuid4(),
        uuid4(),
        uuid4(),
        ModelRoute("GOOGLE_VERTEX", "virtual-try-on-001", "asia-southeast1", "APPAREL", True),
        3,
        NOW + timedelta(minutes=10),
        "preview only",
    )


def test_duplicate_create_returns_one_job_reservation_and_queue_message() -> None:
    jobs, queue, quota = Jobs(), Queue(), Quota()
    service = RenderCommandService(jobs, queue, quota)
    account, principal = uuid4(), uuid4()
    item = quote(account, principal)
    first = service.create(
        item, account_id=account, principal_id=principal, idempotency_key="same", now=NOW
    )
    second = service.create(
        item, account_id=account, principal_id=principal, idempotency_key="same", now=NOW
    )
    assert first == second and queue.ids == [first.job_id] and quota.active == {first.job_id}


def test_success_delivers_private_result_and_consumes_one_allowance() -> None:
    jobs, queue, quota = Jobs(), Queue(), Quota()
    account, principal = uuid4(), uuid4()
    job = RenderCommandService(jobs, queue, quota).create(
        quote(account, principal),
        account_id=account,
        principal_id=principal,
        idempotency_key="one",
        now=NOW,
    )
    result = RenderWorker(jobs, Media(), Provider(), Quality(), Results(), quota).execute(
        job.job_id, now=NOW
    )
    assert (
        result.state == "DELIVERED"
        and result.result_asset_id
        and result.provider_request_id == "req-1"
    )
    assert quota.successes == 1 and not quota.active


def test_quality_failure_never_publishes_or_consumes_allowance() -> None:
    jobs, queue, quota, results = Jobs(), Queue(), Quota(), Results()
    account, principal = uuid4(), uuid4()
    job = RenderCommandService(jobs, queue, quota).create(
        quote(account, principal),
        account_id=account,
        principal_id=principal,
        idempotency_key="one",
        now=NOW,
    )
    result = RenderWorker(jobs, Media(), Provider(), Quality(False), results, quota).execute(
        job.job_id, now=NOW
    )
    assert result.state == "FAILED" and result.failure_code == "QUALITY_REJECTED"
    assert not results.ids and quota.successes == 0 and not quota.active
    assert (
        RenderWorker(jobs, Media(), Provider(), Quality(), results, quota).execute(
            job.job_id, now=NOW
        )
        == result
    )
