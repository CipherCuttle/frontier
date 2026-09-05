from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from frontier.adapters.acquisition.config import RegisteredSource, SourceRegistry
from frontier.application.acquisition import AcquisitionResult
from frontier.application.acquisition_state import SourceFetchState
from frontier.application.worker import AcquisitionWorker, CadenceSlo
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.digests import sha256_digest
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)


class MemoryWorkerRepository:
    def __init__(self, states: dict[str, SourceFetchState | None]) -> None:
        self.states = states
        self.upserted: list[str] = []

    def upsert_source(self, source: SourceContract) -> None:
        self.upserted.append(source.source_id)

    def get_source_fetch_state(self, source_id: str) -> SourceFetchState | None:
        return self.states.get(source_id)


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def acquire(self, source_id: str) -> AcquisitionResult:
        self.calls.append(source_id)
        return AcquisitionResult(
            run_id=UUID(int=len(self.calls)),
            source_id=source_id,
            status=CollectionRunStatus.SUCCESS,
            inserted=1,
            duplicates=0,
            rejected=0,
            observation_ids=(f"obs-{source_id}",),
            failure_code=None,
        )


def registered_source(source_id: str, poll_interval_seconds: int) -> RegisteredSource:
    return RegisteredSource(
        contract=SourceContract(
            source_id=source_id,
            display_name=source_id,
            acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
            signal_roles=(SignalRole.PRIMARY_EMISSION,),
            transport=SourceTransport.REST,
        ),
        endpoint_url=f"https://{source_id}.example/api",
        fallback_urls=(),
        fallback_semantics=None,
        accepted_content_types=("application/json",),
        policy_profile="structured-public-v0",
        authentication="NONE",
        credential_ref=None,
        poll_interval_seconds=poll_interval_seconds,
        finite_window=True,
        etag_support="UNKNOWN",
        last_modified_support="UNKNOWN",
        raw_contract={},
    )


def registry(*sources: RegisteredSource) -> SourceRegistry:
    return SourceRegistry(
        sources={source.contract.source_id: source for source in sources},
        source_registry_version=sha256_digest(b"worker-test-registry"),
    )


def state(
    source_id: str,
    *,
    last_success_at: datetime | None,
    failures: int = 0,
    next_retry_at: datetime | None = None,
) -> SourceFetchState:
    return SourceFetchState(
        source_id=source_id,
        etag=None,
        last_modified=None,
        last_body_digest=None,
        last_success_at=last_success_at,
        consecutive_failures=failures,
        next_retry_at=next_retry_at,
    )


def test_worker_prioritizes_oldest_due_source_and_skips_future_retry() -> None:
    sources = registry(
        registered_source("source.alpha", 60),
        registered_source("source.beta", 60),
        registered_source("source.gamma", 60),
    )
    repo = MemoryWorkerRepository(
        {
            "source.alpha": state("source.alpha", last_success_at=NOW - timedelta(seconds=130)),
            "source.beta": state("source.beta", last_success_at=NOW - timedelta(seconds=300)),
            "source.gamma": state(
                "source.gamma",
                last_success_at=NOW - timedelta(seconds=600),
                failures=2,
                next_retry_at=NOW + timedelta(seconds=20),
            ),
        }
    )
    runner = RecordingRunner()
    worker = AcquisitionWorker(
        registry=sources,
        repository=repo,
        service=runner,
        clock=lambda: NOW,
    )

    cycle = asyncio.run(worker.run_once())

    assert runner.calls == ["source.beta", "source.alpha"]
    assert cycle.skipped_not_due == ("source.gamma",)
    schedules = {schedule.source_id: schedule for schedule in cycle.schedules}
    assert schedules["source.alpha"].cadence_slo is CadenceSlo.BREACHED
    assert schedules["source.beta"].cadence_slo is CadenceSlo.BREACHED
    assert schedules["source.gamma"].cadence_slo is CadenceSlo.BREACHED
    assert schedules["source.gamma"].next_retry_at == NOW + timedelta(seconds=20)


def test_worker_reports_unknown_before_first_success_without_calling_it_healthy() -> None:
    sources = registry(registered_source("source.new", 300))
    repo = MemoryWorkerRepository({"source.new": None})
    runner = RecordingRunner()
    worker = AcquisitionWorker(
        registry=sources,
        repository=repo,
        service=runner,
        clock=lambda: NOW,
    )

    cycle = asyncio.run(worker.run_once())

    assert runner.calls == ["source.new"]
    assert cycle.schedules[0].cadence_slo is CadenceSlo.UNKNOWN
    assert cycle.schedules[0].due
    assert cycle.schedules[0].due_at is None


def test_worker_marks_second_cycle_boundary_at_risk_then_breached() -> None:
    source = registered_source("source.slo", 60)
    sources = registry(source)
    repo = MemoryWorkerRepository(
        {"source.slo": state("source.slo", last_success_at=NOW - timedelta(seconds=120))}
    )
    runner = RecordingRunner()
    worker = AcquisitionWorker(
        registry=sources,
        repository=repo,
        service=runner,
        clock=lambda: NOW,
    )

    at_boundary = asyncio.run(worker.run_once())
    assert at_boundary.schedules[0].cadence_slo is CadenceSlo.AT_RISK

    repo.states["source.slo"] = state(
        "source.slo", last_success_at=NOW - timedelta(seconds=121)
    )
    breached = asyncio.run(worker.run_once())
    assert breached.schedules[0].cadence_slo is CadenceSlo.BREACHED


def test_worker_shortens_sleep_to_earliest_future_due_time() -> None:
    sources = registry(
        registered_source("source.soon", 60),
        registered_source("source.later", 300),
    )
    repo = MemoryWorkerRepository(
        {
            "source.soon": state("source.soon", last_success_at=NOW - timedelta(seconds=50)),
            "source.later": state("source.later", last_success_at=NOW),
        }
    )
    worker = AcquisitionWorker(
        registry=sources,
        repository=repo,
        service=RecordingRunner(),
        clock=lambda: NOW,
        idle_seconds=30,
    )

    assert worker.seconds_until_next_cycle() == 10
